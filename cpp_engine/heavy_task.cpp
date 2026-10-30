// Experimental reversible byte inversion. This is obfuscation, NOT encryption.
#include <array>
#include <fstream>
#include <stdexcept>
#include <string>

bool invert_file_bytes(const std::string &input_path, const std::string &output_path)
{
    if (input_path == output_path)
        throw std::runtime_error("Input and output paths must be different.");

    std::ifstream infile(input_path, std::ios::binary);
    if (!infile)
        throw std::runtime_error("Cannot open input file.");

    std::ofstream outfile(output_path, std::ios::binary | std::ios::trunc);
    if (!outfile)
        throw std::runtime_error("Cannot open output file.");

    // Stream fixed-size chunks to avoid loading the entire file into memory.
    std::array<char, 64 * 1024> buffer{};
    while (infile)
    {
        infile.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto count = infile.gcount();
        for (std::streamsize i = 0; i < count; ++i)
            buffer[static_cast<std::size_t>(i)] = static_cast<char>(~static_cast<unsigned char>(buffer[static_cast<std::size_t>(i)]));
        if (count > 0)
            outfile.write(buffer.data(), count);
        if (!outfile)
            throw std::runtime_error("Failed while writing output file.");
    }
    if (infile.bad())
        throw std::runtime_error("Failed while reading input file.");
    outfile.close();
    if (!outfile)
        throw std::runtime_error("Failed to finalize output file.");
    return true;
}
