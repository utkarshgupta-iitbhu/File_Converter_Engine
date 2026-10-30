#include <pybind11/pybind11.h>
#include <string>

bool invert_file_bytes(const std::string &input_path, const std::string &output_path);
namespace py = pybind11;

PYBIND11_MODULE(cpp_engine, m)
{
    m.doc() = "Experimental streaming byte-inversion utility (not encryption or format conversion).";
    m.def("invert_file_bytes", &invert_file_bytes,
          "Invert each file byte into a separate output file; this is not encryption.",
          py::arg("input_path"), py::arg("output_path"));
}
