#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "DmExternalGeometry.h"

static void check(dm_tv_rect b, double scale, unsigned w, unsigned h) {
    dm_tv_plan p = dm_tv_make_plan(b, scale);
    assert(p.valid && p.pixel_width == w && p.pixel_height == h);
    assert(fabs(p.frame.w / p.frame.h - 16.0 / 9.0) < 1e-10);
    assert(p.frame.x >= b.x && p.frame.y >= b.y);
    assert(p.frame.x + p.frame.w <= b.x + b.w + 1e-8);
    assert(p.frame.y + p.frame.h <= b.y + b.h + 1e-8);
    assert(p.pixel_width <= 1920 && p.pixel_height <= 1080);
    assert(fabs(p.frame.w * p.contents_scale - p.pixel_width) < 1e-8);
    assert(fabs(p.frame.h * p.contents_scale - p.pixel_height) < 1e-8);
}

int main(void) {
    check((dm_tv_rect){0, 0, 1920, 1080}, 1, 1920, 1080);
    check((dm_tv_rect){0, 0, 3840, 2160}, 1, 1920, 1080);
    check((dm_tv_rect){0, 0, 1280, 720}, 1, 1280, 720);
    check((dm_tv_rect){0, 0, 1920, 1080}, 2, 1920, 1080);
    check((dm_tv_rect){0, 0, 1024, 768}, 1, 1024, 576);
    check((dm_tv_rect){0, 0, 3440, 1440}, 1, 1920, 1080);
    check((dm_tv_rect){17, 31, 1024, 768}, 1, 1024, 576);
    check((dm_tv_rect){0, 0, 1080, 1920}, 1, 1072, 603);
    dm_tv_plan p = dm_tv_make_plan((dm_tv_rect){0, 0, 1024, 768}, 1);
    assert(p.frame.x == 0 && p.frame.y == 96);
    p = dm_tv_make_plan((dm_tv_rect){0, 0, 3440, 1440}, 1);
    assert(p.frame.x == 440 && p.frame.y == 0);
    const dm_tv_rect bad[] = {{0, 0, 0, 1080}, {0, 0, 1920, -1},
                              {0, 0, NAN, 1080}, {0, 0, INFINITY, 1080},
                              {NAN, 0, 1920, 1080}, {0, 0, 8, 8}};
    for (unsigned i = 0; i < sizeof bad / sizeof *bad; i++)
        assert(!dm_tv_make_plan(bad[i], 1).valid);
    const double scales[] = {0, -1, NAN, INFINITY};
    for (unsigned i = 0; i < sizeof scales / sizeof *scales; i++)
        assert(!dm_tv_make_plan((dm_tv_rect){0, 0, 1920, 1080}, scales[i]).valid);
    puts("20 external display geometry cases passed");
    return 0;
}
