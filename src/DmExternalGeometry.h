#ifndef DM_EXTERNAL_GEOMETRY_H
#define DM_EXTERNAL_GEOMETRY_H

#include <math.h>

typedef struct { double x, y, w, h; } dm_tv_rect;
typedef struct {
    dm_tv_rect frame;
    unsigned pixel_width, pixel_height;
    double contents_scale;
    int valid;
} dm_tv_plan;

static inline dm_tv_plan dm_tv_make_plan(dm_tv_rect b, double native_scale) {
    dm_tv_plan p = {0};
    if (!isfinite(b.x) || !isfinite(b.y) || !isfinite(b.w) || !isfinite(b.h) ||
        !isfinite(native_scale) || b.w <= 0 || b.h <= 0 || native_scale <= 0) return p;
    double w = b.w, h = b.h;
    if (w / h > 16.0 / 9.0) w = h * 16.0 / 9.0;
    else h = w * 9.0 / 16.0;
    // An integral 16x9 pixel unit keeps both axes at exactly the same scale.
    // Cap before conversion so large or untrusted screen sizes cannot overflow.
    double units = floor(fmin(120.0, fmin(w * native_scale / 16.0,
                                         h * native_scale / 9.0)));
    if (units < 1) return p;
    p.frame = (dm_tv_rect){b.x + floor((b.w - w) / 2),
                          b.y + floor((b.h - h) / 2), w, h};
    p.pixel_width = (unsigned)units * 16;
    p.pixel_height = (unsigned)units * 9;
    p.contents_scale = p.pixel_width / w;
    p.valid = 1;
    return p;
}

#endif
