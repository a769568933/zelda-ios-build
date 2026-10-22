#include <math.h>
#include <stdio.h>
#include <string.h>
#include "../src/DmTouchMotion.h"

// These cases exercise the same C helpers used by DmGamepad, without UIKit.
// A fixed origin, a full-width throw at the left edge, or retained camera
// deltas after a stationary frame must fail their respective regression cases.
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #expr); return 1; } } while (0)
static const dm_pad_rect phone = {0, 0, 874, 402};
static int near(double a, double b) { return fabs(a - b) < 0.00001; }

static int left_area(void) {
    CHECK(dm_pad_left_area((dm_pad_point){18, 250}, phone));
    CHECK(dm_pad_left_area((dm_pad_point){360, 230}, phone));
    CHECK(!dm_pad_left_area((dm_pad_point){18, 100}, phone));
    CHECK(!dm_pad_left_area((dm_pad_point){600, 300}, phone));
    CHECK(!dm_pad_left_area((dm_pad_point){-1, 300}, phone));
    CHECK(!dm_pad_left_area((dm_pad_point){20, 403}, phone));
    return 0;
}
static int touch_origin(void) {
    dm_pad_stick s = {0}; int32_t x, y;
    dm_pad_stick_begin(&s, (dm_pad_point){270, 270});
    CHECK(near(s.center.x, 270) && near(s.center.y, 270));
    dm_pad_stick_axes(&s, phone, 1, 60, &x, &y);
    CHECK(x == 0 && y == 0); // touching down alone never moves the character
    return 0;
}
static int edge_left(void) {
    dm_pad_stick s = {0}; int32_t x, y;
    dm_pad_stick_begin(&s, (dm_pad_point){24, 290});
    dm_pad_stick_move(&s, (dm_pad_point){6, 290}, 60);
    dm_pad_stick_axes(&s, phone, 1, 60, &x, &y);
    CHECK(x == -32767 && y == 0); // full left before the finger leaves the display
    double scale = phone.h / 430;
    dm_pad_stick_begin(&s, (dm_pad_point){6, 250});
    dm_pad_stick_move(&s, (dm_pad_point){0, 250}, 60 * scale);
    dm_pad_stick_axes(&s, phone, scale, 60 * scale, &x, &y);
    CHECK(x == -32767 && y == 0); // even less than the normal minimum throw remains reachable
    return 0;
}
static int following_center(void) {
    dm_pad_stick s = {0};
    dm_pad_stick_begin(&s, (dm_pad_point){180, 250});
    dm_pad_stick_move(&s, (dm_pad_point){300, 250}, 60);
    CHECK(near(s.center.x, 240) && near(s.center.y, 250));
    dm_pad_stick_move(&s, (dm_pad_point){160, 250}, 60);
    CHECK(near(s.center.x, 220));
    int32_t x, y; dm_pad_stick_axes(&s, phone, 1, 60, &x, &y);
    CHECK(x == -32767 && y == 0);
    return 0;
}
static int dead_zone_and_diagonal(void) {
    dm_pad_stick s = {0}; int32_t x, y;
    dm_pad_stick_begin(&s, (dm_pad_point){180, 250});
    dm_pad_stick_move(&s, (dm_pad_point){181, 251}, 60);
    dm_pad_stick_axes(&s, phone, 1, 60, &x, &y); CHECK(x == 0 && y == 0);
    dm_pad_stick_move(&s, (dm_pad_point){220, 210}, 60);
    dm_pad_stick_axes(&s, phone, 1, 60, &x, &y);
    CHECK(x > 23000 && y > 23000 && hypot(x, y) <= 32768);
    return 0;
}
static int stick_release(void) {
    dm_pad_stick s = {0}; int32_t x, y;
    dm_pad_stick_begin(&s, (dm_pad_point){180, 250});
    dm_pad_stick_move(&s, (dm_pad_point){220, 250}, 60);
    dm_pad_stick_end(&s);
    dm_pad_stick_axes(&s, phone, 1, 60, &x, &y); CHECK(x == 0 && y == 0);
    dm_pad_stick_begin(&s, (dm_pad_point){300, 320});
    dm_pad_stick_axes(&s, phone, 1, 60, &x, &y); CHECK(x == 0 && y == 0);
    return 0;
}
static int scaled_phone(void) {
    dm_pad_stick a = {0}, b = {0}; int32_t ax, ay, bx, by;
    dm_pad_stick_begin(&a, (dm_pad_point){180, 250});
    dm_pad_stick_begin(&b, (dm_pad_point){360, 500});
    dm_pad_stick_move(&a, (dm_pad_point){200, 250}, 60);
    dm_pad_stick_move(&b, (dm_pad_point){400, 500}, 120);
    dm_pad_stick_axes(&a, phone, 1, 60, &ax, &ay);
    dm_pad_stick_axes(&b, (dm_pad_rect){0, 0, 1748, 804}, 2, 120, &bx, &by);
    CHECK(ax == bx && ay == by);
    CHECK(dm_pad_left_area((dm_pad_point){130, 230}, (dm_pad_rect){10, 20, 300, 402}));
    return 0;
}
static int camera_area(void) {
    CHECK(dm_pad_right_area((dm_pad_point){450, 200}, phone));
    CHECK(!dm_pad_right_area((dm_pad_point){400, 200}, phone));
    CHECK(!dm_pad_right_area((dm_pad_point){900, 200}, phone));
    return 0;
}
static int camera_motion_and_stop(void) {
    dm_pad_swipe s = {0}; int32_t x, y;
    dm_pad_swipe_begin(&s, (dm_pad_point){600, 200});
    dm_pad_swipe_axes(&s, 1.0 / 60, 1, &x, &y); CHECK(x == 0 && y == 0);
    dm_pad_swipe_move(&s, (dm_pad_point){604, 196});
    dm_pad_swipe_axes(&s, 1.0 / 60, 1, &x, &y); CHECK(x > 0 && y > 0);
    dm_pad_swipe_axes(&s, 1.0 / 60, 1, &x, &y); CHECK(x == 0 && y == 0);
    return 0;
}
static int camera_sample_rate(void) {
    dm_pad_swipe a = {0}, b = {0}; int32_t ax, ay, bx, by;
    dm_pad_swipe_begin(&a, (dm_pad_point){600, 200});
    dm_pad_swipe_begin(&b, (dm_pad_point){600, 200});
    dm_pad_swipe_move(&a, (dm_pad_point){604, 200});
    dm_pad_swipe_move(&b, (dm_pad_point){602, 200});
    dm_pad_swipe_move(&b, (dm_pad_point){604, 200});
    dm_pad_swipe_axes(&a, 1.0 / 60, 1, &ax, &ay);
    dm_pad_swipe_axes(&b, 1.0 / 60, 1, &bx, &by); CHECK(ax == bx && ay == by);
    dm_pad_swipe_move(&b, (dm_pad_point){606, 200});
    dm_pad_swipe_axes(&b, 1.0 / 120, 1, &bx, &by); CHECK(ax == bx);
    return 0;
}
static int camera_release(void) {
    dm_pad_swipe s = {0}; int32_t x, y;
    dm_pad_swipe_begin(&s, (dm_pad_point){600, 200});
    dm_pad_swipe_move(&s, (dm_pad_point){800, 20});
    dm_pad_swipe_end(&s);
    dm_pad_swipe_axes(&s, 1.0 / 60, 1, &x, &y); CHECK(x == 0 && y == 0);
    dm_pad_swipe_move(&s, (dm_pad_point){700, 100});
    dm_pad_swipe_axes(&s, 1.0 / 60, 1, &x, &y); CHECK(x == 0 && y == 0);
    return 0;
}
static int concurrent_move_and_camera(void) {
    dm_pad_stick left = {0}; dm_pad_swipe right = {0}; int32_t lx, ly, rx, ry;
    dm_pad_stick_begin(&left, (dm_pad_point){180, 250});
    dm_pad_stick_move(&left, (dm_pad_point){220, 250}, 60);
    dm_pad_swipe_begin(&right, (dm_pad_point){600, 200});
    dm_pad_swipe_move(&right, (dm_pad_point){604, 200});
    dm_pad_swipe_axes(&right, 1.0 / 60, 1, &rx, &ry); CHECK(rx > 0);
    dm_pad_swipe_end(&right);
    dm_pad_stick_axes(&left, phone, 1, 60, &lx, &ly); CHECK(lx > 0 && ly == 0);
    return 0;
}
static int camera_clamp_and_reverse(void) {
    dm_pad_swipe s = {0}; int32_t x, y;
    dm_pad_swipe_begin(&s, (dm_pad_point){600, 200});
    dm_pad_swipe_move(&s, (dm_pad_point){800, 100});
    dm_pad_swipe_axes(&s, 1.0 / 60, 1, &x, &y); CHECK(x == 32767 && y == 32767);
    dm_pad_swipe_move(&s, (dm_pad_point){796, 100});
    dm_pad_swipe_axes(&s, 1.0 / 60, 1, &x, &y); CHECK(x < 0 && y == 0);
    return 0;
}
int main(void) {
    int (*cases[])(void) = {left_area, touch_origin, edge_left, following_center,
        dead_zone_and_diagonal, stick_release, scaled_phone, camera_area,
        camera_motion_and_stop, camera_sample_rate, camera_release,
        concurrent_move_and_camera, camera_clamp_and_reverse};
    for (unsigned i = 0; i < sizeof cases / sizeof *cases; i++) if (cases[i]()) return 1;
    puts("13 touch-motion regression cases passed"); return 0;
}
