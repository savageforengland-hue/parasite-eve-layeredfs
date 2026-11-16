# CMakeLists.txt for mods/pe_layeredfs (khasinski/parasite-eve-pc v0.12-alpha+ -DPE_MODS=ON)
target_sources(parasite-eve-pc PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/pe_layeredfs.c
)
target_compile_definitions(parasite-eve-pc PRIVATE PE_LAYEREDFS_NATIVE_MOD=1)
