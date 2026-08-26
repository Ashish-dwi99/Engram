// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * High-Performance Data-Driven Flat Compiled Graph
 * 
 * This module implements a CompiledGraph using a zero-overhead Struct-of-Arrays (SoA)
 * memory layout to maximize cache locality, minimize GC churn, and support fast graph
 * traversal and optimization.
 * 
 * The data schemas are defined dynamically in CELL_SCHEMA, PIN_SCHEMA, NET_SCHEMA,
 * and LUT_SCHEMA. Each schema defines the underlying typed array layouts and initialization defaults.
 */

import { PRIMITIVES, getNumericValue, optimizeLUT } from './primitives.js';
import { SoA, range } from './utils.js';

export const CELL_TYPES = {
    INPUT: 1,
    OUTPUT: 2,
    LUT: 3,
    MORPHO: 4
};


// LUT slots (one output wire of a broadcast LUT cell) are identified in optimization
// worklists by the index of the net they drive: netStart[cell] + slot. This key is
// unique per slot, never overflows, and self-invalidates: a bypassed or dead slot
// has net.driverCell === -1, so stale worklist entries are skipped naturally.

/// Memory Layout: Cells (Nodes)
const CELL_SCHEMA = {
    // 1 if active, 0 if deleted
    active: [Uint8Array, 0],
    // Cell type: INPUT, OUTPUT, LUT, MORPHO
    type: [Uint8Array, 0],
    // Truth table value, 0 represents hierarchical complex cell
    lutValue: [Uint32Array, 0],
    // Arity (input port count) of this cell if it is a LUT, otherwise 0
    lutArity: [Uint8Array, 0],
    // Index of parent cell, or -1
    parent: [Int32Array, -1],
    // Start index of inputs in the global input-only pins array.
    // For hierarchical cells, layout is port-ordered (buses stored sequentially).
    // For LUT cells, layout is slot-ordered ([slot, port] contiguous) to enable zero-allocation splitting.
    pinStart: [Int32Array, 0],
    // Total input pins belonging to this cell
    inputCount: [Int32Array, 0],
    // Total output signature width of this cell
    outputCount: [Int32Array, 0],
    // Total active outputs remaining for dead-code checking
    activeOutputs: [Int32Array, 0],
    // Start index in the global nets array of the contiguous output nets driven by this cell, or -1
    netStart: [Int32Array, -1],
    // Time when the first input signal arrives at this cell
    firstTime: [Float32Array, 0],
    // Time when the last input signal arrives at this cell
    lastTime: [Float32Array, 0]
};

// Memory Layout: Pins (Logical Input Terminals only)
// Logical input terminals are stored sequentially from cell.pinStart[cellIdx].
// - Hierarchical: Inputs are port-ordered. Indexed as: cell.pinStart[cellIdx] + (sum of widths of previous ports) + wireIdx
// - LUT cell: Inputs are slot-ordered. Indexed as: cell.pinStart[cellIdx] + (slotIdx * lutArity) + portIdx
const PIN_SCHEMA = {
    // Index of the cell this input pin belongs to
    cell: [Int32Array, -1],
    // Initial local net index assigned to this pin
    net: [Int32Array, -1],
    // Circular linked-list pointer to next destination input pin on the same net
    nextDst: [Int32Array, -1],
    // Circular linked-list pointer to previous destination input pin on the same net
    prevDst: [Int32Array, -1]
};

// Memory Layout: Nets (Physical connections)
const NET_SCHEMA = {
    // Index of the first destination input pin, or -1
    firstDstPin: [Int32Array, -1],
    // Driving cell index, or -1 if driven by constant / global input
    driverCell: [Int32Array, -1],
    // Number of destination input pins connected to this net
    fanout: [Int32Array, 0]
};

class CompiledGraph {
    constructor(initialCapacity = 16) {
        this.name = "";
        this.maxFanout = null;

        this.cell = new SoA(CELL_SCHEMA, initialCapacity);
        this.cell.name = []; // Parallel JS array for strings
        this.cell.def = []; // Parallel JS array: template CompiledGraph of MORPHO cells

        this.pin = new SoA(PIN_SCHEMA, initialCapacity * 4);
        this.net = new SoA(NET_SCHEMA, initialCapacity * 4, 2); // Reserving 0 and 1 for constants
        this.net.name = ["ZERO", "ONE"];

        // Global IO
        this.inputCells = [];
        this.outputCells = [];

        // Optimization worklists: mutations enqueue candidates, commitOptimizations()
        // drains them; stale entries self-invalidate and are skipped at drain time.
        this.dirtyLutSlots = [];
        this.deadNets = [];
    }

    commitOptimizations() {
        this.propagateLUTs();
        this.propagateDCE();
    }

    clearWorklists() {
        this.dirtyLutSlots.length = 0;
        this.deadNets.length = 0;
    }

    optimize() {
        this._queueCellsForOptimization(range(this.cell.count, i => i));
        for (let i = 2; i < this.net.count; i++) {
            if (this.net.fanout[i] === 0 && this.net.driverCell[i] !== -1) {
                this.deadNets.push(i);
            }
        }
        this.commitOptimizations();
    }

    // Signal arrival times via an iterative Kahn topological sweep over the flat arrays
    // (no recursion, no stack-depth limit). Cells on cycles, should they ever appear,
    // are never released and keep time 0.
    updateTimes() {
        const count = this.cell.count;
        const firstTime = this.cell.firstTime.fill(0);
        const lastTime = this.cell.lastTime.fill(0);

        const isTimedDriver = d => d !== -1 &&
            this.cell.active[d] === 1 && this.cell.type[d] !== CELL_TYPES.INPUT;
        const isTimedCell = c =>
            this.cell.active[c] === 1 && this.cell.type[c] !== CELL_TYPES.INPUT;

        // indeg[c] = number of input pins fed by a not-yet-timed driver
        const indeg = new Int32Array(count);
        const queue = new Int32Array(count); // each timed cell is enqueued exactly once
        let head = 0, tail = 0;

        for (let c = 0; c < count; c++) {
            if (!isTimedCell(c)) continue;
            const start = this.cell.pinStart[c];
            const countIn = this.cell.inputCount[c];
            for (let i = 0; i < countIn; i++) {
                const netIdx = this.pin.net[start + i];
                if (netIdx > 1 && isTimedDriver(this.net.driverCell[netIdx])) indeg[c]++;
            }
            if (indeg[c] === 0) queue[tail++] = c;
        }

        while (head < tail) {
            const c = queue[head++];

            // All timed drivers of c are final: compute its arrival window
            const start = this.cell.pinStart[c];
            const countIn = this.cell.inputCount[c];
            let minT = countIn > 0 ? Infinity : 0;
            let maxT = countIn > 0 ? -Infinity : 0;
            for (let i = 0; i < countIn; i++) {
                const netIdx = this.pin.net[start + i];
                let t = 0;
                if (netIdx > 1) {
                    const d = this.net.driverCell[netIdx];
                    if (isTimedDriver(d)) t = lastTime[d] + 1;
                }
                minT = Math.min(minT, t);
                maxT = Math.max(maxT, t);
            }
            firstTime[c] = minT;
            lastTime[c] = maxT;

            // Release consumers of c's output nets
            const netStart = this.cell.netStart[c];
            const outCount = this.cell.outputCount[c];
            for (let j = 0; j < outCount; j++) {
                const netIdx = netStart + j;
                if (this.net.driverCell[netIdx] !== c) continue; // bypassed slot
                let pinIdx = this.net.firstDstPin[netIdx];
                if (pinIdx === -1) continue;
                const startPin = pinIdx;
                do {
                    const k = this.pin.cell[pinIdx];
                    if (isTimedCell(k) && --indeg[k] === 0) queue[tail++] = k;
                    pinIdx = this.pin.nextDst[pinIdx];
                } while (pinIdx !== startPin);
            }
        }
    }

    // Hot path during expansion (_expandMorpho): plain loops, no closure allocation
    get inputs() {
        return this.inputCells.map(c => {
            const start = this.cell.netStart[c];
            const count = this.cell.outputCount[c];
            const nets = [];
            for (let i = 0; i < count; i++) nets.push(start + i);
            return nets;
        });
    }

    get inputSignature() {
        return this.inputCells.map(c => this.cell.outputCount[c]);
    }

    get inputNames() {
        return this.inputCells.map(c => this.cell.name[c]);
    }

    get outputSignature() {
        return this.outputCells.map(c => this.cell.inputCount[c]);
    }

    get outputNames() {
        return this.outputCells.map(c => this.cell.name[c]);
    }

    get outputs() {
        return this.outputCells.map(c => {
            const port = [];
            const start = this.cell.pinStart[c];
            for (let i = 0; i < this.cell.inputCount[c]; i++) {
                port.push(this.pin.net[start + i]);
            }
            return port;
        });
    }

    isSystemCell(cellIdx) {
        const t = this.cell.type[cellIdx];
        return t === CELL_TYPES.INPUT || t === CELL_TYPES.OUTPUT;
    }

    getCellEstimateSize(cellIdx) {
        const t = this.cell.type[cellIdx];
        const outputCount = this.cell.outputCount[cellIdx];
        if (t === CELL_TYPES.LUT || t === CELL_TYPES.INPUT) {
            return outputCount;
        } else if (t === CELL_TYPES.OUTPUT) {
            return this.cell.inputCount[cellIdx] * 2; // boost output node expansion
        }
        const lutCount = this.cell.def[cellIdx]?.estimateLUTCount || 0;
        return Math.max(lutCount, outputCount);
    }

    getLutPinIndex(cellIdx, portIdx, slotIdx) {
        const arity = this.cell.lutArity[cellIdx];
        return this.cell.pinStart[cellIdx] + slotIdx * arity + portIdx;
    }

    getLutSlotFromPinIndex(cellIdx, pinIdx) {
        const arity = this.cell.lutArity[cellIdx];
        return ((pinIdx - this.cell.pinStart[cellIdx]) / arity) | 0;
    }

    pushLutInputPins(cellIdx, inputNets, outputWidth, arity) {
        for (let slotIdx = 0; slotIdx < outputWidth; slotIdx++) {
            for (let portIdx = 0; portIdx < arity; portIdx++) {
                this.addPin(cellIdx, inputNets[portIdx][slotIdx]);
            }
        }
    }

    getNetIndex(cellIdx, wireIdx) {
        return this.cell.netStart[cellIdx] + wireIdx;
    }

    /**
     * Collects all active consumer LUT cell slot keys of a net.
     * @param {number} netIdx - The net index.
     * @param {number[]} [out=[]] - Optional array to collect into.
     * @returns {number[]} The array of consumer slot keys (each slot's output net index).
     */
    collectActiveLutConsumers(netIdx, out = []) {
        const pins = this.getNetPins(netIdx);
        for (const pinIdx of pins) {
            const cellIdx = this.pin.cell[pinIdx];
            if (this.cell.active[cellIdx] === 1 && this.isLut(cellIdx)) {
                const slotIdx = this.getLutSlotFromPinIndex(cellIdx, pinIdx);
                out.push(this.getNetIndex(cellIdx, slotIdx));
            }
        }
        return out;
    }

    /**
     * Collects all destination pins of a net.
     * @param {number} netIdx - The net index.
     * @returns {number[]} The array of pin indices.
     */
    getNetPins(netIdx) {
        const dstPins = [];
        let pinIdx = this.net.firstDstPin[netIdx];
        if (pinIdx === -1) return dstPins;
        const startPin = pinIdx;
        do {
            dstPins.push(pinIdx);
            pinIdx = this.pin.nextDst[pinIdx];
        } while (pinIdx !== startPin);
        return dstPins;
    }

    /**
     * Connects an input pin to a net.
     * @param {number} pinIdx - The pin index.
     * @param {number} netIdx - The net index.
     */
    connectPin(pinIdx, netIdx) {
        this.pin.net[pinIdx] = netIdx; // Store root net index directly

        const first = this.net.firstDstPin[netIdx];
        if (first === -1) {
            this.net.firstDstPin[netIdx] = pinIdx;
            this.pin.nextDst[pinIdx] = pinIdx; // self-loop
            this.pin.prevDst[pinIdx] = pinIdx; // self-loop
        } else {
            const next = this.pin.nextDst[first];
            
            this.pin.nextDst[pinIdx] = next;
            this.pin.prevDst[next] = pinIdx;
            
            this.pin.nextDst[first] = pinIdx;
            this.pin.prevDst[pinIdx] = first;
        }
        this.net.fanout[netIdx]++;
    }

    /**
     * Disconnects an input pin from its net.
     * @param {number} pinIdx - The pin index.
     */
    disconnectPin(pinIdx) {
        const netIdx = this.pin.net[pinIdx];
        if (netIdx === -1) return;
        const next = this.pin.nextDst[pinIdx];
        const prev = this.pin.prevDst[pinIdx];
        
        if (next === pinIdx) {
            // Only pin in the net
            this.net.firstDstPin[netIdx] = -1;
        } else {
            this.pin.nextDst[prev] = next;
            this.pin.prevDst[next] = prev;
            if (this.net.firstDstPin[netIdx] === pinIdx) {
                this.net.firstDstPin[netIdx] = next;
            }
        }
        
        // Reset pointers to self-loop
        this.pin.nextDst[pinIdx] = pinIdx;
        this.pin.prevDst[pinIdx] = pinIdx;
        this.pin.net[pinIdx] = -1;
        this.net.fanout[netIdx]--;
        // Report nets that lost their last destination as DCE candidates
        if (this.net.fanout[netIdx] === 0 && netIdx >= 2 && this.net.driverCell[netIdx] !== -1) {
            this.deadNets.push(netIdx);
        }
    }

    /**
     * Merges net B into net A by updating pin net pointers and merging rings.
     * @param {number} netIdxA - Destination net index.
     * @param {number} netIdxB - Source net index.
     */
    mergeNets(netIdxA, netIdxB) {
        if (netIdxA === netIdxB) return;
        
        const firstB = this.net.firstDstPin[netIdxB];
        // Update all pins pointing to netIdxB to point to netIdxA
        const pinsB = this.getNetPins(netIdxB);
        for (const pinIdx of pinsB) {
            this.pin.net[pinIdx] = netIdxA;
        }
        
        // Merge circular linked lists of destination pins
        const firstA = this.net.firstDstPin[netIdxA];
        if (firstA === -1) {
            this.net.firstDstPin[netIdxA] = firstB;
        } else if (firstB !== -1) {
            const nextA = this.pin.nextDst[firstA];
            const nextB = this.pin.nextDst[firstB];
            
            this.pin.nextDst[firstA] = nextB;
            this.pin.prevDst[nextB] = firstA;
            
            this.pin.nextDst[firstB] = nextA;
            this.pin.prevDst[nextA] = firstB;
        }
        this.net.firstDstPin[netIdxB] = -1;

        if (!this.net.name[netIdxA] && this.net.name[netIdxB]) {
            this.net.name[netIdxA] = this.net.name[netIdxB];
        }
        this.net.driverCell[netIdxB] = -1;
        
        this.net.fanout[netIdxA] += this.net.fanout[netIdxB];
        this.net.fanout[netIdxB] = 0;
    }

    addPin(cellIdx, netIdx) {
        const pinIdx = this.pin.alloc(1);
        this.pin.cell[pinIdx] = cellIdx;
        this.pin.nextDst[pinIdx] = pinIdx; // Starts as self-loop
        this.pin.prevDst[pinIdx] = pinIdx; // Starts as self-loop
        if (netIdx !== -1) this.connectPin(pinIdx, netIdx);
        return pinIdx;
    }

    /**
     * Pushes a new cell and its pins to the graph.
     * @param {string} name - Cell name.
     * @param {number[][]} inputNets - inputNets[port][wire] = netIdx.
     * @param {number[]} outputSignature - Width of each output port.
     * @param {Object} [opts] - Optional cell metadata:
     *   lut {value, arity} - LUT properties; def - template CompiledGraph of a MORPHO cell;
     *   parent - parent cell index.
     * @returns {number[][]} The allocated output net indices for each port & wire of the cell.
     */
    pushCell(name, inputNets, outputSignature, type, { lut = null, def = null, parent = -1 } = {}) {
        const isLut = lut !== null;
        const cellIdx = this.cell.alloc(1);

        this.cell.active[cellIdx] = 1;
        this.cell.type[cellIdx] = type;
        this.cell.name[cellIdx] = name;
        this.cell.lutValue[cellIdx] = isLut ? lut.value : 0;
        this.cell.lutArity[cellIdx] = isLut ? lut.arity : 0;
        this.cell.def[cellIdx] = def;
        this.cell.parent[cellIdx] = parent;

        const numInputs = inputNets.reduce((a, b) => a + b.length, 0);
        const numOutputs = outputSignature.reduce((a, b) => a + b, 0);

        this.cell.pinStart[cellIdx] = this.pin.count;
        this.cell.inputCount[cellIdx] = numInputs;
        this.cell.outputCount[cellIdx] = numOutputs;
        this.cell.activeOutputs[cellIdx] = numOutputs;

        if (isLut) {
            this.pushLutInputPins(cellIdx, inputNets, numOutputs, lut.arity);
        } else {
            for (const bus of inputNets) {
                for (const netIdx of bus) {
                    this.addPin(cellIdx, netIdx);
                }
            }
        }

        // Allocate output nets contiguously in a single block
        const firstNetIdx = this.net.alloc(numOutputs);
        this.cell.netStart[cellIdx] = firstNetIdx;
        for (let i = 0; i < numOutputs; i++) {
            const netIdx = firstNetIdx + i;
            this.net.driverCell[netIdx] = cellIdx;
            this.net.name[netIdx] = "";
        }

        let currNet = firstNetIdx;
        return outputSignature.map(w => range(w, () => currNet++));
    }

    isLut(idx) {
        return this.cell.type[idx] === CELL_TYPES.LUT;
    }

    _getHighFanoutNets(cellIdx) {
        if (this.maxFanout === null) return [];
        const netStart = this.cell.netStart[cellIdx];
        const outCount = this.cell.outputCount[cellIdx];
        if (netStart === -1) return [];

        const bigNets = [];
        for (let j = 0; j < outCount; j++) {
            const netIdx = netStart + j;
            if (this.net.fanout[netIdx] > this.maxFanout) {
                bigNets.push(netIdx);
            }
        }
        return bigNets;
    }

    _queueCellsForOptimization(cellIndices) {
        for (const cellIdx of cellIndices) {
            if (this.cell.active[cellIdx] === 1 && this.isLut(cellIdx)) {
                const width = this.cell.outputCount[cellIdx];
                for (let slotIdx = 0; slotIdx < width; slotIdx++) {
                    this.dirtyLutSlots.push(this.getNetIndex(cellIdx, slotIdx));
                }
            }
        }
    }

    isExpandable(idx) {
        if (this.cell.active[idx] === 0) return false;
        const t = this.cell.type[idx];
        if (t === CELL_TYPES.INPUT || t === CELL_TYPES.LUT) {
            if (this.cell.outputCount[idx] > 1) return true;
        }
        if (t === CELL_TYPES.OUTPUT) {
            if (this.cell.inputCount[idx] > 1) return true;
        }
        if (t === CELL_TYPES.MORPHO) return true;

        if (this._getHighFanoutNets(idx).length > 0) return true;
        return false;
    }

    _mapChildCells(innerGraph, innerToOuterCell, innerToOuterNet, targetCellIdx) {
        for (let i = 0; i < innerGraph.cell.count; i++) {
            if (innerGraph.cell.active[i] === 0 || innerGraph.isSystemCell(i)) continue;

            const outer = this._cloneCellMetadata(i, targetCellIdx, innerGraph);
            innerToOuterCell[i] = outer;

            const outCount = innerGraph.cell.outputCount[i];
            this.cell.outputCount[outer] = outCount;
            this.cell.activeOutputs[outer] = outCount;

            if (outCount === 0) continue;

            const outerNetStart = this.net.alloc(outCount);
            this.cell.netStart[outer] = outerNetStart;
            
            for (let j = 0; j < outCount; j++) {
                const innerNetIdx = innerGraph.cell.netStart[i] + j;
                const outerNetIdx = outerNetStart + j;
                innerToOuterNet[innerNetIdx] = outerNetIdx;
                this.net.driverCell[outerNetIdx] = outer;
                this.net.name[outerNetIdx] = innerGraph.net.name[innerNetIdx];
            }
        }
    }

    _mapChildPins(innerGraph, innerToOuterCell, innerToOuterNet) {
        for (let i = 0; i < innerGraph.cell.count; i++) {
            if (innerGraph.cell.active[i] === 0 || innerGraph.isSystemCell(i)) continue;

            const outer = innerToOuterCell[i];
            const inCount = innerGraph.cell.inputCount[i];

            this.cell.pinStart[outer] = this.pin.count;
            this.cell.inputCount[outer] = inCount;

            const pinStart = innerGraph.cell.pinStart[i];
            for (let j = 0; j < inCount; j++) {
                const innerNet = innerGraph.pin.net[pinStart + j];
                const outerNet = (innerNet !== -1) ? (innerToOuterNet[innerNet] ?? -1) : -1;
                this.addPin(outer, outerNet);
            }
        }
    }

    _mergeGlobalIO(innerGraph, innerToOuterNet, targetNetStart) {
        const innerOutputs = innerGraph.outputs.flat();
        for (let i = 0; i < innerOutputs.length; i++) {
            const innerNet = innerOutputs[i];
            const outerNet = (innerNet !== -1) ? (innerToOuterNet[innerNet] ?? -1) : -1;
            if (outerNet !== -1) this.mergeNets(outerNet, targetNetStart + i);
        }
    }

    _disconnectParentCell(targetCellIdx) {
        const targetPinStart = this.cell.pinStart[targetCellIdx];
        const targetInputCount = this.cell.inputCount[targetCellIdx];
        for (let i = 0; i < targetInputCount; i++) {
            this.disconnectPin(targetPinStart + i);
        }
        // Deactivate the cell itself
        this.cell.active[targetCellIdx] = 0;
    }

    /**
     * Expands a cell by one growth step: inlines a hierarchical cell's template graph,
     * splits a multi-wire IO/LUT cell in half, or buffers its high-fanout nets.
     * @param {number} targetCellIdx - Index of cell to expand.
     * @param {boolean} optimize - Run optimizations cascadingly after expansion.
     * @returns {boolean} True if expansion succeeded, false otherwise.
     */
    expandCell(targetCellIdx, optimize = false) {
        if (!this.isExpandable(targetCellIdx)) return false;

        const expanded = this._expandStep(targetCellIdx);
        if (optimize) this.commitOptimizations();
        else this.clearWorklists();
        return expanded;
    }

    _expandStep(targetCellIdx) {
        const t = this.cell.type[targetCellIdx];

        // 1. Hierarchical cells: inline the child template graph
        if (t === CELL_TYPES.MORPHO) return this._expandMorpho(targetCellIdx);

        // 2. Split multi-output or multi-input cells
        const width = t === CELL_TYPES.OUTPUT ?
            this.cell.inputCount[targetCellIdx] : this.cell.outputCount[targetCellIdx];
        if (width > 1) return this._splitCell(targetCellIdx);

        // 3. Buffer high-fanout nets of leaf cells
        const bigNets = this._getHighFanoutNets(targetCellIdx);
        if (bigNets.length === 0) return false;
        this._queueCellsForOptimization(this._bufferCellNets(targetCellIdx, bigNets));
        return true;
    }

    _expandMorpho(targetCellIdx) {
        const innerGraph = this.cell.def[targetCellIdx];
        if (!innerGraph) return false;

        const targetPinStart = this.cell.pinStart[targetCellIdx];
        const targetNetStart = this.cell.netStart[targetCellIdx];
        const targetInputCount = this.cell.inputCount[targetCellIdx];
        const targetOutputCount = this.cell.outputCount[targetCellIdx];

        const parentInputNets = [];
        for (let i = 0; i < targetInputCount; i++) {
            const netIdx = this.pin.net[targetPinStart + i];
            if (netIdx >= 2) parentInputNets.push(netIdx);
        }

        // Re-evaluate consumers of the parent's outputs once they are re-driven
        // (enqueued unconditionally; expandCell commits or discards the worklists)
        for (let i = 0; i < targetOutputCount; i++) {
            this.collectActiveLutConsumers(targetNetStart + i, this.dirtyLutSlots);
        }

        // Initialize mapping array for child nets to parent nets
        const innerToOuterNet = new Int32Array(innerGraph.net.count).fill(-1);
        innerToOuterNet[0] = 0;
        innerToOuterNet[1] = 1;

        // Map child global inputs to parent inputs
        const innerInputs = innerGraph.inputs.flat();
        for (let i = 0; i < innerInputs.length; i++) {
            const innerRootInputNet = innerInputs[i];
            if (innerRootInputNet < 2) continue;
            innerToOuterNet[innerRootInputNet] = this.pin.net[targetPinStart + i];
        }

        const innerToOuterCell = new Int32Array(innerGraph.cell.count).fill(-1);
        const firstNewCellIdx = this.cell.count;
        const firstNewNetIdx = this.net.count;

        this._mapChildCells(innerGraph, innerToOuterCell, innerToOuterNet, targetCellIdx);
        this._mapChildPins(innerGraph, innerToOuterCell, innerToOuterNet);
        this._mergeGlobalIO(innerGraph, innerToOuterNet, targetNetStart);
        this._disconnectParentCell(targetCellIdx);

        // Queue new LUT cells and born-dead nets (outputs whose consumers were masked out)
        this._queueCellsForOptimization(
            range(this.cell.count - firstNewCellIdx, i => firstNewCellIdx + i));
        for (let netIdx = firstNewNetIdx; netIdx < this.net.count; netIdx++) {
            if (this.net.fanout[netIdx] === 0) this.deadNets.push(netIdx);
        }

        // Buffer parent input nets driven by previously visited cells
        if (this.maxFanout !== null) {
            const driverToBigNets = new Map();
            for (const netIdx of parentInputNets) {
                if (this.net.fanout[netIdx] > this.maxFanout) {
                    const driver = this.net.driverCell[netIdx];
                    if (driver !== -1 && this.cell.active[driver] === 1 && driver < targetCellIdx) {
                        if (!driverToBigNets.has(driver)) {
                            driverToBigNets.set(driver, []);
                        }
                        driverToBigNets.get(driver).push(netIdx);
                    }
                }
            }
            for (const [driver, bigNets] of driverToBigNets) {
                this._queueCellsForOptimization(this._bufferCellNets(driver, bigNets));
            }
        }

        return true;
    }

    _cloneCellMetadata(srcCellIdx, parentCellIdx = srcCellIdx, srcGraph = this) {
        const c = this.cell.alloc(1);
        this.cell.active[c] = 1;
        this.cell.type[c] = srcGraph.cell.type[srcCellIdx];
        this.cell.name[c] = srcGraph.cell.name[srcCellIdx];
        this.cell.lutValue[c] = srcGraph.cell.lutValue[srcCellIdx];
        this.cell.lutArity[c] = srcGraph.cell.lutArity[srcCellIdx];
        this.cell.def[c] = srcGraph.cell.def[srcCellIdx];
        this.cell.parent[c] = parentCellIdx;
        return c;
    }

    _setCellSlice(parentCellIdx, pStart, nStart, width, arity, isOutputCell) {
        let activeCount = 0;
        
        if (isOutputCell) {
            activeCount = 0;
        } else if (nStart !== -1) {
            for (let i = 0; i < width; i++) {
                if (this.net.driverCell[nStart + i] !== -1) activeCount++;
            }
            if (activeCount === 0) {
                for (let i = 0; i < width * arity; i++) {
                    this.disconnectPin(pStart + i);
                }
                return -1;
            }
        }
        
        const cIdx = this._cloneCellMetadata(parentCellIdx);
        this.cell.pinStart[cIdx] = pStart;
        
        if (isOutputCell) {
            this.cell.inputCount[cIdx] = width;
            this.cell.netStart[cIdx] = -1;
            this.cell.outputCount[cIdx] = 0;
            this.cell.activeOutputs[cIdx] = 0;
        } else {
            this.cell.inputCount[cIdx] = width * arity;
            this.cell.netStart[cIdx] = nStart;
            this.cell.outputCount[cIdx] = width;
            this.cell.activeOutputs[cIdx] = activeCount;
        }
        
        const pinCount = isOutputCell ? width : width * arity;
        for (let i = 0; i < pinCount; i++) {
            this.pin.cell[pStart + i] = cIdx;
        }
        
        if (!isOutputCell && nStart !== -1) {
            for (let i = 0; i < width; i++) {
                if (this.net.driverCell[nStart + i] !== -1) {
                    this.net.driverCell[nStart + i] = cIdx;
                }
            }
        }
        
        return cIdx;
    }

    _splitCell(cellIdx) {
        if (this.cell.active[cellIdx] === 0) return false;

        const name = this.cell.name[cellIdx];
        let S = 0;
        let arity = 0;

        const isOutput = this.cell.type[cellIdx] === CELL_TYPES.OUTPUT; 
        if (isOutput) {
            S = this.cell.inputCount[cellIdx];
            arity = 1;
        } else {
            S = this.cell.outputCount[cellIdx];
            arity = this.cell.lutArity[cellIdx];
        }
        
        if (S <= 1) return false;
        
        const pStart = this.cell.pinStart[cellIdx];
        const nStart = this.cell.netStart[cellIdx];
        const S1 = Math.floor(S / 2);
        
        // Deactivate parent cell
        this.cell.active[cellIdx] = 0;
        this.cell.activeOutputs[cellIdx] = 0;

        this._setCellSlice(cellIdx, pStart, nStart, S1, arity, isOutput);
        this._setCellSlice(cellIdx, pStart + S1 * arity, nStart === -1 ? -1 : nStart + S1, S - S1, arity, isOutput);
        
        return true;
    }

    /**
     * Performs cascading forward constant/buffer propagation, draining the dirtyLutSlots
     * worklist. Queues consumer slots of any bypassed slots to enable complete
     * non-topological constant propagation.
     */
    propagateLUTs() {
        const worklist = this.dirtyLutSlots;
        if (worklist.length === 0) return;

        const queued = new Set(worklist);

        while (worklist.length > 0) {
            const outNet = worklist.pop();
            queued.delete(outNet);

            // Slot keys are output net indices: resolve the owning cell from the driver.
            const cellIdx = this.net.driverCell[outNet];
            if (cellIdx === -1) continue; // Slot already dead or bypassed
            if (this.cell.active[cellIdx] === 0) continue;
            const slotIdx = outNet - this.cell.netStart[cellIdx];

            const arity = this.cell.lutArity[cellIdx];
            const lutVal = this.cell.lutValue[cellIdx];

            const slotWires = [];
            for (let portIdx = 0; portIdx < arity; portIdx++) {
                slotWires.push(this.pin.net[this.getLutPinIndex(cellIdx, portIdx, slotIdx)]);
            }
            const [replacement, externalUseMask] = optimizeLUT(lutVal, slotWires);

            // Preserve fanout buffers from collapsing back into their driver
            const isBuf = lutVal === 2 && arity === 1;
            if (replacement >= 2 && this.maxFanout !== null && isBuf && this.net.fanout[outNet] > 1) {
                continue;
            }

            // Disconnect unused input pins for this slot (disconnectPin queues dead nets)
            for (let portIdx = 0; portIdx < arity; portIdx++) {
                if ((externalUseMask & (1 << portIdx)) === 0) {
                    this.disconnectPin(this.getLutPinIndex(cellIdx, portIdx, slotIdx));
                }
            }

            if (replacement === -1) continue;

            // Slot collapsed: bypass and merge
            const consumers = this.collectActiveLutConsumers(outNet);

            this.mergeNets(replacement, outNet);

            this.cell.activeOutputs[cellIdx]--;
            if (this.cell.activeOutputs[cellIdx] === 0) {
                this.cell.active[cellIdx] = 0;
            }

            // Queue consumer slots for re-evaluation
            for (const consumerKey of consumers) {
                if (!queued.has(consumerKey)) {
                    queued.add(consumerKey);
                    worklist.push(consumerKey);
                }
            }
        }
    }

    /**
     * Performs cascading progressive Dead Code Elimination (DCE), draining the deadNets
     * worklist. disconnectPin feeds it whenever a net loses its last destination pin,
     * so upstream nets freed by the eliminations below cascade automatically.
     */
    propagateDCE() {
        const worklist = this.deadNets;
        while (worklist.length > 0) {
            const netIdx = worklist.pop();

            const driver = this.net.driverCell[netIdx];
            if (driver === -1) continue; // Already dead/processed (or a constant net)
            if (this.net.fanout[netIdx] !== 0) continue; // Reconnected since queuing

            // Mark net as dead by removing its driver cell reference
            this.net.driverCell[netIdx] = -1;

            if (this.isSystemCell(driver)) continue;
            if (this.cell.active[driver] === 0) continue;

            const isLut = this.isLut(driver);
            if (isLut) {
                // LUT cell: immediately disconnect inputs of this slot
                const slotIdx = netIdx - this.cell.netStart[driver];
                const arity = this.cell.lutArity[driver];

                for (let portIdx = 0; portIdx < arity; portIdx++) {
                    this.disconnectPin(this.getLutPinIndex(driver, portIdx, slotIdx));
                }
            }

            this.cell.activeOutputs[driver]--;
            if (this.cell.activeOutputs[driver] === 0) {
                this.cell.active[driver] = 0;
                if (!isLut) {
                    // Complex cell: disconnect all its inputs
                    const pinStart = this.cell.pinStart[driver];
                    const numInputs = this.cell.inputCount[driver];
                    for (let i = 0; i < numInputs; i++) {
                        this.disconnectPin(pinStart + i);
                    }
                }
            }
        }
    }

    _splitIntoGroups(array, k) {
        const result = [];
        let remaining = array.length;
        let offset = 0;
        for (let i = 0; i < k; i++) {
            const size = Math.ceil(remaining / (k - i));
            result.push(array.slice(offset, offset + size));
            offset += size;
            remaining -= size;
        }
        return result;
    }

    _bufferCellNets(driverCellIdx, bigNets) {
        const allDstPins = bigNets.map(netIdx => this.getNetPins(netIdx));

        const inputNets = [ bigNets ];
        const outputSignature = [ bigNets.length ];
        const numGroups = 3;

        const maxFanoutInCell = Math.max(...allDstPins.map(p => p.length));
        const actualGroups = Math.min(numGroups, maxFanoutInCell, this.maxFanout);

        const partitionedPins = [];
        for (let i = 0; i < bigNets.length; i++) {
            partitionedPins.push(this._splitIntoGroups(allDstPins[i], actualGroups));
        }

        const groupBufNets = [];
        const newBufCells = [];
        for (let g = 0; g < actualGroups; g++) {
            const bufNets = this.pushCell("BUF", inputNets, outputSignature, CELL_TYPES.LUT,
                { lut: { value: 2, arity: 1 }, parent: driverCellIdx });
            groupBufNets.push(bufNets[0]);
            newBufCells.push(this.cell.count - 1);
        }

        for (let i = 0; i < bigNets.length; i++) {
            for (let g = 0; g < actualGroups; g++) {
                const bufNetIdx = groupBufNets[g][i];
                for (const pin of partitionedPins[i][g]) {
                    this.disconnectPin(pin);
                    this.connectPin(pin, bufNetIdx);
                }
            }
        }

        return newBufCells;
    }
}

const CONSTANTS = { ZERO: [0], ONE: [1], VOID: [] };

function resolveArgNets(arg, varNets) {
    if (!arg) return [];
    if (CONSTANTS[arg]) return CONSTANTS[arg];
    if (varNets[arg] !== undefined) return varNets[arg];
    
    if (/^(?:\d+|0b[01_]+|0x[0-9a-fA-F_]+)$/.test(arg)) {
        return Array.from(getNumericValue(arg).toString(2), c => parseInt(c, 10)).reverse();
    }
    throw new Error(`Unknown identifier: ${arg}`);
}

function materializeLut(graph, op, inputs, lutDef) {
    if (inputs.some(bus => bus.length === 0)) return null;
    const w = Math.max(...inputs.map(x => x.length));

    // Broadcast/replicate scalar inputs (width 1) to match vector width w
    const broadcastedInputs = inputs.map(bus =>
        (bus.length === 1 && w > 1) ? Array(w).fill(bus[0]) : bus);

    return graph.pushCell(op, broadcastedInputs, [w], CELL_TYPES.LUT, {
        lut: { value: lutDef.value, arity: inputs.length }
    });
}

function materializeCell(graph, op, inputs, context) {
    const sig = inputs.map(x => x.length);
    const sub = materialize(op, sig, context);
    if (!sub) return null;

    // Mask unused inputs in the submodule with -1 to let parent DCE eliminate dead drivers early
    const maskedInputs = inputs.map((portBus, i) => {
        const subPortBus = sub.inputs[i];
        return portBus.map((outerNet, j) => {
            const innerNet = subPortBus[j];
            return sub.net.fanout[innerNet] === 0 ? -1 : outerNet;
        });
    });

    return graph.pushCell(sigKey(sub.name, sig), maskedInputs, sub.outputSignature,
        CELL_TYPES.MORPHO, { def: sub });
}

// Signature-keyed name of a cell specialization, e.g. "ripple_adder:[4,4,1]"
const sigKey = (name, sig) => `${name}:[${sig.join(',')}]`;

function processSSAInstruction(graph, inst, context, varNets) {
    const resolve = arg => resolveArgNets(arg, varNets);
    const op = inst.op;

    if (PRIMITIVES[op]) return PRIMITIVES[op](inst.args, resolve);

    const inputs = inst.args.map(resolve);
    if (context.lutMap.has(op)) return materializeLut(graph, op, inputs, context.lutMap.get(op));

    const targetOp = context.cellOverrides?.[op] || op;
    if (context.cellMap.has(targetOp)) {
        const childContext = inst.overrides
            ? { ...context, cellOverrides: { ...context.cellOverrides, ...inst.overrides } }
            : context;
        return materializeCell(graph, targetOp, inputs, childContext);
    }

    throw new Error(`Unknown operation: ${op}`);
}

// Shared prologue: a fresh graph with one input cell per input port
function createGraph(name, inputNames, sig, context) {
    const graph = new CompiledGraph();
    graph.name = name;
    graph.maxFanout = context.maxFanout;
    inputNames.forEach((inp, i) => {
        graph.pushCell(inp, [], [sig[i]], CELL_TYPES.INPUT);
        graph.inputCells.push(graph.cell.count - 1);
    });
    return graph;
}

// Shared: append one OUTPUT cell per output port
function addOutputCells(graph, outputNames, outputNets) {
    outputNames.forEach((outName, i) => {
        graph.pushCell(outName, [outputNets[i]], [], CELL_TYPES.OUTPUT);
        graph.outputCells.push(graph.cell.count - 1);
    });
}

// Shared epilogue: one output cell per output port, then optimize and size-estimate
function finalizeGraph(graph, outputNames, outputNets, context) {
    addOutputCells(graph, outputNames, outputNets);
    if (context.optimize) graph.optimize();
    graph.estimateLUTCount = computeEstimateLUTCount(graph);
    return graph;
}

// Executes the cell's SSA body into a fresh graph.
// Returns null if a boundary was hit (the graph is discarded; the fallback decides).
function buildCellBody(cellDef, sig, context) {
    const graph = createGraph(cellDef.name, cellDef.inputs, sig, context);
    const varNets = {};
    cellDef.inputs.forEach((inp, i) => varNets[inp] = graph.inputs[i]);

    for (const inst of cellDef.ssa) {
        const targets = processSSAInstruction(graph, inst, context, varNets);
        if (!targets) return null;
        inst.targets.forEach((t, i) => varNets[t] = targets[i]);
    }
    const outputNets = cellDef.outputs.map(arg => resolveArgNets(arg, varNets));
    return finalizeGraph(graph, cellDef.outputs, outputNets, context);
}

// Resolves a triggered fallback: no fallback -> null; positional index -> a pristine
// pass-through graph wiring input #fbIdx straight to the output; name -> the fallback cell.
function materializeFallback(cellDef, sig, context) {
    if (cellDef.fallback == null) return null;
    const fbIdx = parseInt(cellDef.fallback, 10);
    if (isNaN(fbIdx)) return materialize(cellDef.fallback, sig, context);

    const graph = createGraph(cellDef.name, cellDef.inputs, sig, context);
    return finalizeGraph(graph, [cellDef.inputs[fbIdx]], [graph.inputs[fbIdx]], context);
}

const computeEstimateLUTCount = (graph) => {
    let count = 0;
    for (let cellIdx = 0; cellIdx < graph.cell.count; cellIdx++) {
        if (graph.cell.active[cellIdx] === 0 || graph.isSystemCell(cellIdx)) continue;
        count += graph.getCellEstimateSize(cellIdx);
    }
    return count;
};

function materialize(name, sig, context) {
    const overriddenName = context.cellOverrides?.[name] || name;
    const key = sigKey(overriddenName, sig);
    if (context.registry.has(key)) return context.registry.get(key);

    const cellDef = context.cellMap.get(overriddenName);
    if (!cellDef) throw new Error(`Unknown cell: ${overriddenName}`);

    const graph = buildCellBody(cellDef, sig, context) ?? materializeFallback(cellDef, sig, context);
    context.registry.set(key, graph);
    return graph;
}

function compileModule(parsedModule, rootName, rootInputSignature,
                       optimize = false, maxFanout = null) {
    const registry = new Map();
    const rootCompiled = materialize(rootName, rootInputSignature, {
        cellMap: new Map(parsedModule.cells.map(c => [c.name, c])),
        lutMap: new Map(parsedModule.luts.map(l => [l.name, l])),
        registry,
        optimize, maxFanout
    });

    const createRoot = () => {
        const graph = createGraph(rootName, rootCompiled.inputNames, rootInputSignature,
                                  { maxFanout });

        // A single unexpanded MORPHO cell (no optimize/estimate needed)
        const mainOutputs = graph.pushCell(sigKey(rootName, rootInputSignature), graph.inputs,
            rootCompiled.outputSignature, CELL_TYPES.MORPHO, { def: rootCompiled });
        addOutputCells(graph, rootCompiled.outputNames, mainOutputs);

        return graph;
    };

    return { registry, createRoot };
}

export { CompiledGraph, compileModule, PRIMITIVES };
