const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

class LowPassFilter {
    constructor(alpha, initialValue = null) {
        this.alpha = alpha;
        this.initialized = initialValue !== null;
        this.value = initialValue;
    }

    filter(nextValue, alpha = this.alpha) {
        this.alpha = alpha;
        if (!this.initialized) {
            this.value = nextValue;
            this.initialized = true;
            return nextValue;
        }
        this.value = alpha * nextValue + (1 - alpha) * this.value;
        return this.value;
    }

    reset(nextValue = null) {
        this.initialized = nextValue !== null;
        this.value = nextValue;
    }
}

class OneEuroFilter {
    constructor({
        minCutoff = 1.2,
        beta = 0.03,
        derivativeCutoff = 1.8
    } = {}) {
        this.minCutoff = minCutoff;
        this.beta = beta;
        this.derivativeCutoff = derivativeCutoff;
        this.valueFilter = new LowPassFilter(this._alpha(minCutoff));
        this.derivativeFilter = new LowPassFilter(this._alpha(derivativeCutoff), 0);
        this.lastTimestampMs = null;
        this.lastRawValue = null;
    }

    _alpha(cutoff, dt = 1 / 60) {
        const tau = 1 / (2 * Math.PI * cutoff);
        return 1 / (1 + tau / dt);
    }

    filter(rawValue, timestampMs) {
        if (this.lastTimestampMs === null) {
            this.lastTimestampMs = timestampMs;
            this.lastRawValue = rawValue;
            this.valueFilter.reset(rawValue);
            this.derivativeFilter.reset(0);
            return rawValue;
        }

        const dt = Math.max((timestampMs - this.lastTimestampMs) / 1000, 1 / 240);
        const rawDerivative = (rawValue - this.lastRawValue) / dt;
        const derivative = this.derivativeFilter.filter(
            rawDerivative,
            this._alpha(this.derivativeCutoff, dt)
        );
        const cutoff = this.minCutoff + this.beta * Math.abs(derivative);
        const filtered = this.valueFilter.filter(rawValue, this._alpha(cutoff, dt));

        this.lastTimestampMs = timestampMs;
        this.lastRawValue = rawValue;
        return filtered;
    }

    reset(nextValue = null, timestampMs = null) {
        this.valueFilter.reset(nextValue);
        this.derivativeFilter.reset(0);
        this.lastRawValue = nextValue;
        this.lastTimestampMs = timestampMs;
    }
}

export class OneEuroFilter2D {
    constructor(config = {}) {
        this.xFilter = new OneEuroFilter(config);
        this.yFilter = new OneEuroFilter(config);
    }

    filter(point, timestampMs) {
        return {
            x: this.xFilter.filter(point.x, timestampMs),
            y: this.yFilter.filter(point.y, timestampMs),
        };
    }

    reset(point = null, timestampMs = null) {
        this.xFilter.reset(point?.x ?? null, timestampMs);
        this.yFilter.reset(point?.y ?? null, timestampMs);
    }
}

export const DEFAULT_HAND_CONTROL_CONFIG = {
    interactionBox: {
        left: 0.18,
        right: 0.82,
        top: 0.16,
        bottom: 0.84,
    },
    filter: {
        minCutoff: 1.1,
        beta: 0.035,
        derivativeCutoff: 1.7,
    },
    cursor: {
        deadZone: 0.0065,
        precisionGain: 0.6,
        turboGain: 2.2,
        accelerationExponent: 1.55,
        maxStepPx: 56,
        outputBlend: 0.45,
        freezeMs: 110,
    },
    gestures: {
        holdMs: 90,
        releaseMs: 75,
        clutchHoldMs: 110,
        clickCooldownMs: 650,
        pinchStartRatio: 0.46,
        pinchEndRatio: 0.62,
        scrollStepPx: 18,
    },
};

export const clampPointToInteractionBox = (point, box = DEFAULT_HAND_CONTROL_CONFIG.interactionBox) => {
    const clampedX = clamp(point.x, box.left, box.right);
    const clampedY = clamp(point.y, box.top, box.bottom);
    return {
        x: (clampedX - box.left) / Math.max(box.right - box.left, 0.001),
        y: (clampedY - box.top) / Math.max(box.bottom - box.top, 0.001),
        rawClamped: { x: clampedX, y: clampedY },
        inside:
            point.x >= box.left &&
            point.x <= box.right &&
            point.y >= box.top &&
            point.y <= box.bottom,
    };
};

export class CursorEngine {
    constructor(config = DEFAULT_HAND_CONTROL_CONFIG.cursor) {
        this.config = config;
        this.cursorX = null;
        this.cursorY = null;
        this.targetX = null;
        this.targetY = null;
        this.previousPoint = null;
        this.freezeUntilMs = 0;
    }

    reset(viewport = null) {
        this.previousPoint = null;
        this.freezeUntilMs = 0;
        if (viewport) {
            this.cursorX = viewport.width / 2;
            this.cursorY = viewport.height / 2;
            this.targetX = this.cursorX;
            this.targetY = this.cursorY;
        } else {
            this.cursorX = null;
            this.cursorY = null;
            this.targetX = null;
            this.targetY = null;
        }
    }

    freeze(timestampMs, durationMs = this.config.freezeMs) {
        this.freezeUntilMs = Math.max(this.freezeUntilMs, timestampMs + durationMs);
    }

    update({
        point,
        timestampMs,
        viewport,
        sensitivity = 1,
        clutch = false,
    }) {
        if (this.cursorX === null || this.cursorY === null) {
            this.cursorX = viewport.width / 2;
            this.cursorY = viewport.height / 2;
            this.targetX = this.cursorX;
            this.targetY = this.cursorY;
        }

        if (!this.previousPoint) {
            this.previousPoint = point;
            return {
                x: this.cursorX,
                y: this.cursorY,
                moved: false,
                delta: { x: 0, y: 0 },
            };
        }

        const deltaX = point.x - this.previousPoint.x;
        const deltaY = point.y - this.previousPoint.y;
        this.previousPoint = point;

        if (clutch || timestampMs < this.freezeUntilMs) {
            this.targetX = this.cursorX;
            this.targetY = this.cursorY;
            return {
                x: this.cursorX,
                y: this.cursorY,
                moved: false,
                delta: { x: 0, y: 0 },
            };
        }

        const magnitude = Math.hypot(deltaX, deltaY);
        if (magnitude <= this.config.deadZone) {
            this.targetX = this.cursorX;
            this.targetY = this.cursorY;
            return {
                x: this.cursorX,
                y: this.cursorY,
                moved: false,
                delta: { x: 0, y: 0 },
            };
        }

        const normalizedMagnitude = clamp(
            (magnitude - this.config.deadZone) / Math.max(1 - this.config.deadZone, 0.001),
            0,
            1
        );
        const gain =
            (this.config.precisionGain +
                (this.config.turboGain - this.config.precisionGain) *
                    Math.pow(normalizedMagnitude, this.config.accelerationExponent)) *
            sensitivity;

        let moveX = deltaX * viewport.width * gain;
        let moveY = deltaY * viewport.height * gain;
        const stepMagnitude = Math.hypot(moveX, moveY);
        if (stepMagnitude > this.config.maxStepPx) {
            const scale = this.config.maxStepPx / stepMagnitude;
            moveX *= scale;
            moveY *= scale;
        }

        this.targetX = clamp(this.targetX + moveX, 0, viewport.width);
        this.targetY = clamp(this.targetY + moveY, 0, viewport.height);
        this.cursorX += (this.targetX - this.cursorX) * this.config.outputBlend;
        this.cursorY += (this.targetY - this.cursorY) * this.config.outputBlend;

        return {
            x: this.cursorX,
            y: this.cursorY,
            moved: true,
            delta: { x: moveX, y: moveY },
        };
    }
}

export class GestureStateMachine {
    constructor(config = DEFAULT_HAND_CONTROL_CONFIG.gestures) {
        this.config = config;
        this.state = 'IDLE';
        this.candidate = 'TRACKING';
        this.candidateSinceMs = 0;
        this.releaseSinceMs = 0;
        this.lastClickAtMs = 0;
    }

    reset() {
        this.state = 'IDLE';
        this.candidate = 'TRACKING';
        this.candidateSinceMs = 0;
        this.releaseSinceMs = 0;
    }

    _setCandidate(candidate, timestampMs) {
        if (candidate !== this.candidate) {
            this.candidate = candidate;
            this.candidateSinceMs = timestampMs;
        }
    }

    _candidateStable(timestampMs, holdMs) {
        return timestampMs - this.candidateSinceMs >= holdMs;
    }

    _handleRelease(timestampMs, shouldRelease) {
        if (!shouldRelease) {
            this.releaseSinceMs = 0;
            return false;
        }
        if (!this.releaseSinceMs) {
            this.releaseSinceMs = timestampMs;
            return false;
        }
        return timestampMs - this.releaseSinceMs >= this.config.releaseMs;
    }

    update(signals, timestampMs) {
        if (!signals.handPresent) {
            this.reset();
            return { state: 'IDLE', action: null, confidence: 0 };
        }

        let action = null;
        let candidate = 'TRACKING';
        if (signals.clutch) {
            candidate = 'CLUTCH';
        } else if (signals.drag) {
            candidate = 'DRAG';
        } else if (signals.scroll) {
            candidate = 'SCROLL';
        } else if (signals.pinch) {
            candidate = 'CLICK_CANDIDATE';
        }

        this._setCandidate(candidate, timestampMs);

        if (this.state === 'IDLE') {
            this.state = 'TRACKING';
        }

        if (this.state === 'TRACKING') {
            if (candidate === 'CLUTCH' && this._candidateStable(timestampMs, this.config.clutchHoldMs)) {
                this.state = 'CLUTCH';
            } else if (candidate === 'DRAG' && this._candidateStable(timestampMs, this.config.holdMs)) {
                this.state = 'DRAG';
                action = 'drag_start';
            } else if (candidate === 'SCROLL' && this._candidateStable(timestampMs, this.config.holdMs)) {
                this.state = 'SCROLL';
            } else if (candidate === 'CLICK_CANDIDATE' && this._candidateStable(timestampMs, this.config.holdMs)) {
                this.state = 'CLICK_CANDIDATE';
            }
        } else if (this.state === 'CLICK_CANDIDATE') {
            const released = this._handleRelease(timestampMs, !signals.pinch);
            if (released) {
                if (timestampMs - this.lastClickAtMs >= this.config.clickCooldownMs) {
                    this.lastClickAtMs = timestampMs;
                    action = 'click';
                }
                this.state = 'TRACKING';
                this.releaseSinceMs = 0;
            }
        } else if (this.state === 'DRAG') {
            if (this._handleRelease(timestampMs, !signals.drag)) {
                this.state = 'TRACKING';
                this.releaseSinceMs = 0;
                action = 'drag_end';
            }
        } else if (this.state === 'SCROLL') {
            if (this._handleRelease(timestampMs, !signals.scroll)) {
                this.state = 'TRACKING';
                this.releaseSinceMs = 0;
            }
        } else if (this.state === 'CLUTCH') {
            if (this._handleRelease(timestampMs, !signals.clutch)) {
                this.state = 'TRACKING';
                this.releaseSinceMs = 0;
            }
        }

        const confidence = clamp(
            (timestampMs - this.candidateSinceMs) / Math.max(this.config.holdMs, 1),
            0,
            1
        );

        return {
            state: this.state,
            action,
            confidence,
        };
    }
}

export { clamp };
