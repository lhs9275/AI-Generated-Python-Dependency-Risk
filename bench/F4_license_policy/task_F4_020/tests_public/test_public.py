import inspect
from plotter import plot_scatter
def test_callable(): assert callable(plot_scatter)
def test_param_count(): assert len(inspect.signature(plot_scatter).parameters) == 3
