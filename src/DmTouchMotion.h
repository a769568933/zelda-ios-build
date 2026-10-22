#ifndef DM_TOUCH_MOTION_H
#define DM_TOUCH_MOTION_H

#include <math.h>
#include <stdint.h>

// UIKit supplies points, bounds and scale. Keeping the input math independent
// of the view lets the edge reach and the release/stop behavior run on any host.
typedef struct { double x, y; } dm_pad_point;
typedef struct { double x, y, w, h; } dm_pad_rect;
typedef struct { dm_pad_point center, point; int active; } dm_pad_stick;
typedef struct { dm_pad_point last, pending; int active; } dm_pad_swipe;

static inline int dm_pad_contains(dm_pad_point p, dm_pad_rect b) {
    return b.w > 0 && b.h > 0 && p.x >= b.x && p.y >= b.y && p.x <= b.x + b.w && p.y <= b.y + b.h;
}
static inline int dm_pad_left_area(dm_pad_point p, dm_pad_rect b) {
    return dm_pad_contains(p, b) && p.x <= b.x + b.w * 0.45 && p.y >= b.y + b.h * 0.40;
}
static inline int dm_pad_right_area(dm_pad_point p, dm_pad_rect b) {
    return dm_pad_contains(p, b) && p.x >= b.x + b.w * 0.50;
}
static inline void dm_pad_stick_begin(dm_pad_stick *s, dm_pad_point p) {
    *s = (dm_pad_stick){.center = p, .point = p, .active = 1};
}
static inline void dm_pad_stick_move(dm_pad_stick *s, dm_pad_point p, double radius) {
    if (!s->active || radius <= 0) return;
    s->point = p;
    double dx = p.x - s->center.x, dy = p.y - s->center.y, d = hypot(dx, dy);
    if (d > radius) s->center = (dm_pad_point){p.x - dx * radius / d, p.y - dy * radius / d};
}
static inline void dm_pad_stick_end(dm_pad_stick *s) { *s = (dm_pad_stick){0}; }
static inline void dm_pad_stick_axes(const dm_pad_stick *s, dm_pad_rect b, double scale, double radius, int32_t *x, int32_t *y) {
    *x = *y = 0;
    if (!s->active || radius <= 0 || scale <= 0) return;
    double dx = s->point.x - s->center.x, dy = s->point.y - s->center.y, d = hypot(dx, dy);
    if (d < 0.000001) return;
    // Shorten the full-tilt distance in a direction that meets a screen edge.
    // Moving left can reach full speed before the finger leaves the display;
    // touching down remains neutral even when the origin is near an edge.
    double edge = INFINITY;
    if (dx < 0) edge = fmin(edge, (s->center.x - b.x) * d / -dx);
    if (dx > 0) edge = fmin(edge, (b.x + b.w - s->center.x) * d / dx);
    if (dy < 0) edge = fmin(edge, (s->center.y - b.y) * d / -dy);
    if (dy > 0) edge = fmin(edge, (b.y + b.h - s->center.y) * d / dy);
    double full = fmin(radius * 0.8, fmax(8 * scale, edge - 6 * scale));
    full = fmin(full, edge); // even the minimum throw must fit on the display
    if (full <= 0.000001) return;
    double dead = fmin(4 * scale, full * 0.15);
    if (d <= dead) return;
    double m = fmin((d - dead) / (full - dead), 1) / d;
    *x = (int32_t)lrint(dx * m * 32767);
    *y = (int32_t)lrint(-dy * m * 32767); // host input: up is positive
}

static inline void dm_pad_swipe_begin(dm_pad_swipe *s, dm_pad_point p) {
    *s = (dm_pad_swipe){.last = p, .active = 1};
}
static inline void dm_pad_swipe_move(dm_pad_swipe *s, dm_pad_point p) {
    if (!s->active) return;
    s->pending.x += p.x - s->last.x; s->pending.y += p.y - s->last.y;
    s->last = p;
}
static inline void dm_pad_swipe_end(dm_pad_swipe *s) { *s = (dm_pad_swipe){0}; }
static inline int32_t dm_pad_camera_axis(double speed) {
    return (int32_t)lrint(fmax(-1, fmin(1, speed)) * 32767);
}
static inline void dm_pad_swipe_axes(dm_pad_swipe *s, double seconds, double scale, int32_t *x, int32_t *y) {
    *x = *y = 0;
    if (s->active && isfinite(seconds) && seconds > 0 && scale > 0) {
        double full_speed = 480 * scale; // points per second, independent of touch-event frequency
        *x = dm_pad_camera_axis(s->pending.x / (seconds * full_speed));
        *y = dm_pad_camera_axis(-s->pending.y / (seconds * full_speed));
    }
    s->pending = (dm_pad_point){0}; // a frame without movement reports zero, even with the finger held down
}

#endif
