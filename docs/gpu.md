# GPU rendering (Linux, experimental)

By default the emulator renders in software (SwiftShader). On Linux with a GPU that Mesa drives
(Intel tested; AMD should work the same way), `./lab up --gpu` renders on the GPU instead. On an
Intel N150 that roughly doubled what the page could present (about 15 frames a second instead of
11 on a 15 fps stream), cut a canvas read of a video frame from about 90 to 32 ms, and brought the
fullscreen "blip" into a phone's range. Video decoding stays in software either way.

**Experimental:** the emulator crashed once in an evening of use on this route. Use the default
route for long unattended runs.

## Use

```bash
./lab doctor          # says whether the render node /dev/dri/renderD128 is usable
./lab down
./lab up --gpu
./lab status          # "renderer: ... Mesa Intel(R) Graphics ..." when it works
```

Back to software: `./lab down && ./lab up`. Nothing on the host changes either way.

## How it works

The emulator's OpenGL ES renderer uses GLX, which needs an X display; the container has none with
a GPU. **VirtualGL** (in the image) gives the emulator GLX on a private virtual display while
rendering on the host's render node. VirtualGL 3.1.5 returns 1 instead of 0 from
`glXGetFBConfigAttrib()` for the three pbuffer-size attributes (its EGL back end), which made the
emulator reject every framebuffer config; **`docker/vglfix/vglfix.c`**, built into the image and
loaded first, turns that 1 into 0 for those attributes only. Reported upstream as
[VirtualGL#292](https://github.com/VirtualGL/virtualgl/issues/292); the shim can go once a release
fixes it. Files: `docker/compose.gpu.yml`,
`docker/Dockerfile`, `docker/vglfix/`, `setup/start-emulator.sh`.

If the emulator crashes on this route, its core dump is in the `sdk` volume
(`/opt/android-sdk/core.<pid>`; it holds the guest's memory, tokens included, so never share it), and
the previous log and crash database are kept (`/data/out/emulator.log.1`, `/data/out/crash/`).
