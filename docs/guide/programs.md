# LittleFoot programs

load a `.littlefoot` source file onto a connected Block through the running daemon. loading replaces the active device program temporarily. blocksd does not save it as the startup default.

## Load from the dashboard

open `blocksd ui`, select a device, and find **device program** below its settings. choose a LittleFoot file, then press **load program**. selecting a file alone does not send it to the device.

open **additional include files** if the program imports files outside the bundled LittleFoot library. select those files before loading. each filename must be unique, including the main source filename. the selected files must total no more than 256 KiB.

compiler errors appear in the panel. error line numbers refer to the compiled source after includes are expanded and metadata defaults are added, so they may differ from the selected file's line numbers. after compilation, the status follows the upload. **upload acknowledged** means the device acknowledged the transfer; it does not establish that the application is running correctly. test the program's controls and musical output on your hardware.

## Load from the command line

start the service or `blocksd run`, then find the device serial:

```bash
blocksd status
blocksd program load Seqoli.littlefoot --device SERIAL
blocksd program status --device SERIAL
```

replace `SERIAL` with the serial reported by `blocksd status`. the device option can be omitted when exactly one device is connected. these commands use the daemon's MIDI connection.

the CLI collects referenced local includes from the selected file's directory and its subdirectories. it preserves their relative paths, so `#include "helpers/Patterns.littlefoot"` works when that file is inside the source directory. references outside that directory are not read automatically.

supply additional files explicitly when needed:

```bash
blocksd program load MyProgram.littlefoot --device SERIAL \
  --include Helpers.littlefoot --include Patterns.littlefoot
```

explicit `--include` files are supplied by basename: a source line such as `#include "Helpers.littlefoot"` resolves to the file supplied with that name. conflicting duplicate include names are rejected. the daemon receives the selected source bundle and does not search your filesystem for missing includes.

the bundled library provides `AppleControlSurface.littlefoot`, `ClusterSync.littlefoot`, `ConfigIds.littlefoot`, `NoteGridBase.littlefoot`, `RPNHandler.littlefoot`, and `Scale.littlefoot`. these files do not need a separate upload.

programs written for ROLI Dashboard can declare variables in metadata. blocksd supports declared defaults for `int`, `float`, `bool`, and `midiNote` variables. other metadata types, including `colour` and `option`, are rejected with a compiler error. support for these four types does not establish compatibility with every Dashboard program.

the supported variables become fixed defaults in the compiled program. they do not become editable dashboard settings; changing a declared default requires loading the modified source again.

the compiled program and its declared heap must fit the selected device's memory. source size alone does not predict whether a program fits.

## Restore the saved program

press **restore saved program** on the device page, or run:

```bash
blocksd program reset --device SERIAL
```

the reset requests the program saved on the device and releases blocksd's temporary program ownership. it is not a factory reset. blocksd does not keep a copy of whichever temporary program was running before the load.

lighting requests cannot silently replace a custom program loaded by blocksd. restore the saved program before using `blocksd led` again.

## Diagnose lighting startup

the device program panel also reports the state of blocksd's lighting renderer. **transfer details** contains byte counts and the current transfer message.

| State                   | Meaning                                                                                  |
| ----------------------- | ---------------------------------------------------------------------------------------- |
| uploading               | the device has not acknowledged the complete upload yet                                  |
| waiting for device      | the upload was acknowledged; the renderer has not replied to its execution challenge     |
| renderer ready          | the renderer answered the current challenge; visible output still needs a hardware check |
| device has not answered | the renderer has not replied within the readiness window                                 |

custom programs do not implement blocksd's renderer challenge, so their successful upload is reported separately. if a lighting renderer does not answer, record the device model, firmware, program status, and verbose daemon log before changing the program. an upload acknowledgement alone is not a reason to bypass the challenge.
