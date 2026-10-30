cmake_minimum_required(VERSION 3.15)
project(cpp_engine LANGUAGES CXX)

find_package(pybind11 CONFIG REQUIRED)
pybind11_add_module(cpp_engine bindings.cpp heavy_task.cpp)
target_compile_features(cpp_engine PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(cpp_engine PRIVATE /O2 /W4)
else()
    target_compile_options(cpp_engine PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()
# Place the importable extension beside main.py so `import cpp_engine` works.
set_target_properties(cpp_engine PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/.."
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/.."
    LIBRARY_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_SOURCE_DIR}/.."
    LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}/.."
    RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_SOURCE_DIR}/.."
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}/.."
)
