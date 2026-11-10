#include <juce_core/juce_core.h>
#include "roli_LittleFootRunner.h"
#include "compiler.h"
#include "prototypes.h"
#include <iostream>
#include <iterator>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

int main()
{
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    const std::string source { std::istreambuf_iterator<char>(std::cin), {} };
    littlefoot::Compiler compiler;
    compiler.addNativeFunctions(nativeFunctions);
    const auto result = compiler.compile(juce::String::fromUTF8(source.data(), static_cast<int>(source.size())), 0);
    if (result.failed())
    {
        std::cerr << result.getErrorMessage() << '\n';
        return 1;
    }
    const auto& code = compiler.compiledObjectCode;
    std::cout.write(reinterpret_cast<const char*>(code.begin()), code.size());
    return std::cout.good() ? 0 : 1;
}
