idf_component_register(SRCS "main.c" "../../mcu/hdc_packed.c"
  INCLUDE_DIRS "../../mcu" "${PROJECT_DIR}/../../build/mcu-vectors"
  REQUIRES esp_timer esp_hw_support)
target_compile_definitions(${COMPONENT_LIB} PRIVATE HDC_CLASSES=${HDC_CLASSES})
target_compile_options(${COMPONENT_LIB} PRIVATE -O3 -fno-lto -fno-builtin
  -fno-tree-loop-distribute-patterns)
