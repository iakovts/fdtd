## Imports

# other
from math import pi, sin

# typing
from .typing import Tuple, Number, ListOrSlice, List

# relatvie
from .grid import Grid
from .backend import backend as bd


## LineSource class
class LineSource:
    """ A source along a line in the grid """
    def __init__(
        self,
        period: Number = 15,
        power: float = 1.0,
        phase_shift: float = 0.0,
        name: str = None,
    ):
        """ Create a LineSource with a gaussian profile

        Args:
            period = 1: The period of the source. The period can be specified
                as integer [timesteps] or as float [seconds]
            power = 1.0: The power of the source
            phase_shift = 0.0: The phase offset of the source.

        Note:
            The initialization of the source is not finished before it is
            registered on the grid.

        """
        self.grid = None
        self.period = period
        self.power = power
        self.phase_shift = phase_shift
        self.name = name

    def _register_grid(
            self,
            grid: Grid,
            x: ListOrSlice,
            y: ListOrSlice,
            z: ListOrSlice
        ):
        """ Register a grid for the source.

        Args:
            grid: The grid to register the source in.
            x: The x-location of the volume in the grid
            y: The y-location of the volume in the grid
            z: The z-location of the volume in the grid

        Note:
            As its name suggests, this source is a LINE source.
            Hence the source spans the diagonal of the cube
            defined by the slices in the grid.
        """
        self.grid = grid
        self.grid._sources.append(self)
        if self.name is not None:
            if not hasattr(grid, self.name):
                setattr(grid, self.name, self)
            else:
                raise ValueError(
                    f"The grid already has an attribute with name {self.name}"
                )

        self.x, self.y, self.z = self._handle_slices(x, y, z)

        self.period = grid._handle_time(self.period)
        amplitude = (
            self.power * self.grid.inverse_permittivity[self.x, self.y, self.z, 2]
        ) ** 0.5

        L = len(self.x)
        self.vect = bd.array(
            (bd.array(self.x) - self.x[L // 2]) ** 2
            + (bd.array(self.y) - self.y[L // 2]) ** 2
            + (bd.array(self.z) - self.z[L // 2]) ** 2,
            bd.float,
        )

        self.profile = bd.exp(-self.vect ** 2 / (2 * (0.5 * self.vect.max()) ** 2))
        self.profile /= self.profile.sum()
        self.profile *= amplitude

    def _handle_slices(
        self,
        x: ListOrSlice,
        y: ListOrSlice,
        z: ListOrSlice
        ) -> Tuple[List, List, List]:
        """ Convert slices in the grid to lists

        This is necessary to make the source span the diagonal of the volume
        defined by the slices.

        Args:
            x: The x-location of the volume in the grid
            y: The y-location of the volume in the grid
            z: The z-location of the volume in the grid

        Returns:
            x, y, z: the x, y and z coordinates of the source as lists

        """

        # if list-indices were chosen:
        if isinstance(x, list) and isinstance(y, list) and isinstance(z, list):
            if len(x) != len(y) or len(y) != len(z) or len(z) != len(x):
                raise IndexError("sources require grid to be indexed with slices or equal length list-indices")
            return x, y, z

        # if a combination of list-indices and slices were chosen,
        # convert the list-indices to slices.
        # TODO: maybe issue a warning here?
        if isinstance(x, list):
            x = slice(x[0], x[-1], None)
        if isinstance(y, list):
            y = slice(y[0], y[-1], None)
        if isinstance(z, list):
            z = slice(z[0], z[-1], None)

        # if we get here, we can assume only well-behaved slices:
        # we convert the slices into index lists
        x0, y0, z0 = x.start, y.start, z.start
        x1, y1, z1 = x.stop, y.stop, z.stop
        m = max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
        x = list(bd.array(bd.linspace(x0, x1, m, endpoint=False), bd.int))
        y = list(bd.array(bd.linspace(y0, y1, m, endpoint=False), bd.int))
        z = list(bd.array(bd.linspace(z0, z1, m, endpoint=False), bd.int))
        return x, y, z

    def update_E(self):
        """ Add the source to the electric field """
        q = self.grid.timesteps_passed
        vect = self.profile * sin(2 * pi * q / self.period + self.phase_shift)
        # do not use list indexing here, as this is much slower especially for torch backend
        # DISABLED: self.grid.E[self.x, self.y, self.z, 2] = self.vect
        for x, y, z, value in zip(self.x, self.y, self.z, vect):
            self.grid.E[x, y, z, 2] += value

    def update_H(self):
        """ Add the source to the magnetic field """
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(period={self.period}, power={self.power}, phase_shift={self.phase_shift}, name={repr(self.name)})"
