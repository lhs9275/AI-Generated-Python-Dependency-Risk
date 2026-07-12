import inspect
from plotter import plot_scatter
def test_output_str():
    ann = inspect.signature(plot_scatter).parameters["output_path"].annotation
    assert ann in (str, "str")
