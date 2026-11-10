cmake_minimum_required(VERSION 3.24)
project(blocksd_littlefoot LANGUAGES CXX)
file(ARCHIVE_EXTRACT INPUT "${CMAKE_CURRENT_SOURCE_DIR}/vendor.tar.gz" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/vendor")
set(juce_SOURCE_DIR "${CMAKE_CURRENT_BINARY_DIR}/vendor")
set(roli_SOURCE_DIR "${CMAKE_CURRENT_BINARY_DIR}/vendor/roli")

# Source includes are resolved from explicitly supplied files by Python. The
# compiler itself must never resolve an uploaded path against the daemon's disk.
file(READ "${roli_SOURCE_DIR}/littlefoot/roli_LittleFootCompiler.h" compiler)
string(FIND "${compiler}" "    static juce::File resolveIncludePath" resolver_start)
string(FIND "${compiler}" "    /** After a successful call to compile(), this contains" resolver_end)
if(resolver_start LESS 0 OR resolver_end LESS resolver_start)
  message(FATAL_ERROR "The pinned compiler include resolver changed")
endif()
string(SUBSTRING "${compiler}" 0 ${resolver_start} compiler_prefix)
string(SUBSTRING "${compiler}" ${resolver_end} -1 compiler_suffix)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/compiler.h"
  "${compiler_prefix}    static juce::File resolveIncludePath (juce::String, juce::Array<juce::File>) { return {}; }\n\n${compiler_suffix}")

file(READ "${roli_SOURCE_DIR}/protocol/roli_BlocksProtocolDefinitions.h" protocol)
string(REGEX MATCHALL "\"[A-Za-z0-9_]+/[vifb]+\"" prototypes "${protocol}")
list(JOIN prototypes ",\n" prototype_lines)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/prototypes.h"
  "static const char* const nativeFunctions[] = {\n${prototype_lines},\nnullptr\n};\n")

add_executable(blocksd-littlefoot main.cpp "${juce_SOURCE_DIR}/juce_core/juce_core.cpp")
target_compile_features(blocksd-littlefoot PRIVATE cxx_std_17)
target_include_directories(blocksd-littlefoot PRIVATE
  "${juce_SOURCE_DIR}" "${roli_SOURCE_DIR}/littlefoot" "${CMAKE_CURRENT_BINARY_DIR}")
target_compile_definitions(blocksd-littlefoot PRIVATE
  JUCE_GLOBAL_MODULE_SETTINGS_INCLUDED=1 JUCE_STANDALONE_APPLICATION=1
  JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_MODAL_LOOPS_PERMITTED=0)
if(APPLE)
  enable_language(OBJCXX)
  set_source_files_properties("${juce_SOURCE_DIR}/juce_core/juce_core.cpp" PROPERTIES LANGUAGE OBJCXX)
  target_link_libraries(blocksd-littlefoot PRIVATE "-framework Cocoa" "-framework Foundation" "-framework IOKit" "-framework Security")
elseif(UNIX)
  target_link_libraries(blocksd-littlefoot PRIVATE dl pthread rt)
endif()
install(TARGETS blocksd-littlefoot RUNTIME DESTINATION .)
