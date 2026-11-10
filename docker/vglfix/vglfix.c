/*
 * vglfix.so: works around VirtualGL 3.1.5's glXGetFBConfigAttrib returning 1 instead of Success (0)
 * for GLX_MAX_PBUFFER_WIDTH/HEIGHT/PIXELS with its EGL back end, while filling in the right value
 * (measured 10-11-2026). The Android emulator's GLX renderer (gfxstream, EglOsApi_glx.cpp) treats
 * any non-zero return as a failure and drops the config: with VirtualGL every config was dropped
 * ("Failed to find exactly 1 GLES 2.x config: found 0").
 *
 * Loaded first (VGL_PRELOAD, see setup/start-emulator.sh). The emulator dlopen()s libGL.so.1 and
 * looks functions up in that handle, so:
 *  - dlopen() of libGL.so* returns this library's own handle; it is linked against VirtualGL's
 *    libvglfaker.so, so a lookup in the handle finds glXGetFBConfigAttrib here and every other GLX
 *    function in VirtualGL (the object first, then its dependencies);
 *  - glXGetFBConfigAttrib() calls the next one (VirtualGL's) and turns a return of 1 into 0 for the
 *    three pbuffer-size attributes only;
 *  - every other dlopen() goes to the next dlopen unchanged. dlsym() is not touched (an earlier
 *    version wrapped it, which broke RTLD_NEXT lookups and crashed the emulator).
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <string.h>

typedef int (*attrib_fn)(void *dpy, void *config, int attribute, int *value);
typedef void *(*dlopen_fn)(const char *file, int flags);

int glXGetFBConfigAttrib(void *dpy, void *config, int attribute, int *value) {
  static attrib_fn next;
  if (!next) next = (attrib_fn)dlsym(RTLD_NEXT, "glXGetFBConfigAttrib");
  if (!next) return 1;
  int r = next(dpy, config, attribute, value);
  /* GLX_MAX_PBUFFER_WIDTH 0x8016, _HEIGHT 0x8017, _PIXELS 0x8018 */
  if (r == 1 && attribute >= 0x8016 && attribute <= 0x8018) return 0;
  return r;
}

void *dlopen(const char *file, int flags) {
  static dlopen_fn next;
  if (!next) next = (dlopen_fn)dlsym(RTLD_NEXT, "dlopen");
  if (file) {
    const char *base = strrchr(file, '/');
    base = base ? base + 1 : file;
    if (strncmp(base, "libGL.so", 8) == 0) {
      Dl_info self;
      if (dladdr((void *)glXGetFBConfigAttrib, &self) && self.dli_fname) return next(self.dli_fname, flags);
    }
  }
  return next(file, flags);
}
