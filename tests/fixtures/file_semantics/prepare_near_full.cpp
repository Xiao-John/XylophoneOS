// SPDX-License-Identifier: Apache-2.0
// Test-only offline image preparation. Fill through real FatFs, then create
// an exclusive output image; never overwrite an existing image or device.
#define main file_semantics_unused_main
#include "file_semantics.cpp"
#undef main

int main(int argc, char** argv) {
    require(argc == 3, "input and new output image arguments");
    FILE* image = std::fopen(argv[1], "rb");
    require(image != nullptr, "open source private image");
    std::fseek(image, 0, SEEK_END);
    original.resize(static_cast<size_t>(std::ftell(image)));
    std::rewind(image);
    require(std::fread(original.data(), 1, original.size(), image) == original.size(), "read source image");
    std::fclose(image);
    reset_media();
    require(fs.csize == 8, "near-full guest fixture uses 4096-byte FAT16 clusters");
    seed_file("nearfull.bin", "keep", 4);
    seed_file("replace_old", "old", 3);
    seed_file("replace_new", "new", 3);
    DWORD available = 0;
    FATFS* volume = nullptr;
    require(f_getfree("", &available, &volume) == FR_OK && available > 1, "free cluster budget");
    FIL filler{};
    require(f_open(&filler, "filler.bin", FA_WRITE | FA_CREATE_NEW) == FR_OK, "filler create");
    unsigned char bytes[4096]{};
    for (DWORD i = 1; i < available; ++i) {
        UINT written = 0;
        require(f_write(&filler, bytes, sizeof(bytes), &written) == FR_OK && written == sizeof(bytes), "real filler write");
    }
    require(f_close(&filler) == FR_OK && f_getfree("", &available, &volume) == FR_OK && available == 1,
            "exactly one real cluster remains");
    image = std::fopen(argv[2], "wbx");
    require(image != nullptr, "create exclusive private output image");
    require(std::fwrite(media.data(), 1, media.size(), image) == media.size(), "write prepared image");
    require(std::fclose(image) == 0, "close prepared image");
    puts("NEAR_FULL_IMAGE_FREE_CLUSTERS=1");
    return 0;
}
