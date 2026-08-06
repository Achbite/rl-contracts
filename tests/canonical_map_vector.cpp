#include <cstdint>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace {

void AppendU32(std::vector<std::uint8_t>& output, std::uint32_t value) {
    output.push_back(static_cast<std::uint8_t>((value >> 24U) & 0xffU));
    output.push_back(static_cast<std::uint8_t>((value >> 16U) & 0xffU));
    output.push_back(static_cast<std::uint8_t>((value >> 8U) & 0xffU));
    output.push_back(static_cast<std::uint8_t>(value & 0xffU));
}

void AppendI32(std::vector<std::uint8_t>& output, std::int32_t value) {
    AppendU32(output, static_cast<std::uint32_t>(value));
}

void AppendBytes(std::vector<std::uint8_t>& output,
                 const std::vector<std::uint8_t>& value) {
    AppendU32(output, static_cast<std::uint32_t>(value.size()));
    output.insert(output.end(), value.begin(), value.end());
}

void AppendString(std::vector<std::uint8_t>& output, const std::string& value) {
    AppendU32(output, static_cast<std::uint32_t>(value.size()));
    output.insert(output.end(), value.begin(), value.end());
}

}  // namespace

int main() {
    std::vector<std::uint8_t> canonical;
    const std::string magic("rl.task.maze.map.v4\0", 20);
    canonical.insert(canonical.end(), magic.begin(), magic.end());
    AppendU32(canonical, 4);
    AppendU32(canonical, 4);
    AppendU32(canonical, 3);
    AppendU32(canonical, 1000000);
    AppendI32(canonical, 0);
    AppendI32(canonical, 0);
    AppendI32(canonical, 3);
    AppendI32(canonical, 2);
    AppendBytes(canonical, {0x12, 0x00});
    AppendString(canonical, "maze.action.9-way.no-corner-cut.v1");

    std::cout << std::hex << std::setfill('0');
    for (const auto byte : canonical) {
        std::cout << std::setw(2) << static_cast<unsigned int>(byte);
    }
    std::cout << '\n';
    return 0;
}
