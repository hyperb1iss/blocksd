# LittleFoot compiler

The wheel includes a standalone compiler executable. Source distributions build
it with CMake and a C++17 compiler. Compilation never downloads dependencies.
Only JUCE's core module is compiled; no audio, GUI, or plug-in modules are used.

## Source provenance and licenses

The deterministic `vendor.tar.gz` archive contains:

- `juce_core/`: the complete `modules/juce_core` directory from JUCE 7.0.12.
  [The pinned module is ISC licensed](https://github.com/juce-framework/JUCE/blob/7.0.12/modules/juce_core/juce_core.h).
  Embedded third-party source files retain their own notices.
- `roli/`: `roli_LittleFootRunner.h`, `roli_LittleFootCompiler.h`,
  `roli_BlocksProtocolDefinitions.h`, and `LICENSE.txt` from the
  [ROLI SDK commit `212ba4e237638b9ae8c2a4f76dd2070110392031`](https://github.com/WeAreROLI/roli_blocks_basics/tree/212ba4e237638b9ae8c2a4f76dd2070110392031).
  These files are ISC licensed.

The archive is included in wheels so the exact source and copyright notices
travel with the binary. The standard scripts in `src/blocksd/littlefoot/library`
come from the same SDK commit and retain its license.

Source archive checksums:

| Archive | SHA-256 |
| --- | --- |
| JUCE 7.0.12 GitHub tag archive | `94e3b35e1990cd67f59736bb5e1eff1cfd9590b16fea82696f309a8f59452434` |
| ROLI SDK GitHub commit archive | `94db1e98f10b8d55984ef248d34f985c9c0ca3218f46df1c183240fb36aad959` |
| Filtered `vendor.tar.gz` | `5fd338765b977557102d62c7cd6c46c552401fe48e2e5fddd5a0235646df1f9e` |

The filtered archive stores files in name order with zero timestamps, UID and
GID zero, mode 0644, and an empty gzip filename. `CMakeLists.txt` generates one
patch at build time: the compiler's filesystem include resolver always returns
an empty file. Python resolves includes from the supplied virtual file map and
bundled library first. A directive missed by that preprocessor fails in the
native compiler instead of reading a file from the daemon's filesystem.

Native function signatures are extracted from the pinned SDK protocol header.
Syntax and native function errors come from the SDK compiler. Reported line
numbers refer to the expanded source, including metadata default declarations.

## Dashboard metadata

Dashboard XML variables are compiled using their declared defaults. Supported
variable types are `int`, `float`, `bool`, and `midiNote` (ROLI's C-2 is MIDI 0).
They become constants. Changing these values requires editing the file and
loading it again; the dashboard does not expose live controls for this metadata.
Unknown types fail with an explicit error instead of being ignored.

The upstream Seqoli source needs its metadata defaults and the bundled
`ClusterSync.littlefoot` / `ConfigIds.littlefoot` includes. Compiling this source
proves language and include compatibility; it does not establish timing or MIDI
behavior on physical hardware. Seqoli itself is not redistributed here.
