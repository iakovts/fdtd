## Imports

# 3rd party
import numpy as np
from tqdm import tqdm

# typing
from .typing import Tuple, Number, Tensorlike

# relative
from .backend import backend as bd


## Constants
SPEED_LIGHT: float = 299_792_458.0  # [m/s] speed of light


## Functions
def curl_E(E: Tensorlike) -> Tensorlike:
    """ Transforms an E-type field into an H-type field by performing a curl
    operation

    Args: E: Electric field to take the curl of (E-type field located on
        integer grid points)

    Returns: curl_E: the curl of E (H-type field located on half-integer grid
        points)
    """
    curl_E = bd.zeros(E.shape)

    curl_E[:, :-1, :, 0] += E[:, 1:, :, 2] - E[:, :-1, :, 2]
    curl_E[:, :, :-1, 0] -= E[:, :, 1:, 1] - E[:, :, :-1, 1]

    curl_E[:, :, :-1, 1] += E[:, :, 1:, 0] - E[:, :, :-1, 0]
    curl_E[:-1, :, :, 1] -= E[1:, :, :, 2] - E[:-1, :, :, 2]

    curl_E[:-1, :, :, 2] += E[1:, :, :, 1] - E[:-1, :, :, 1]
    curl_E[:, :-1, :, 2] -= E[:, 1:, :, 0] - E[:, :-1, :, 0]

    return curl_E


def curl_H(H: Tensorlike) -> Tensorlike:
    """ Transforms an H-type field into an E-type field by performing a curl
    operation

    Args:
        H: Magnetic field to take the curl of (H-type field located on
            half-integer grid points)

    Returns:
        curl_H: the curl of H (E-type field located on integer grid points)
    """
    curl_H = bd.zeros(H.shape)

    curl_H[:, 1:, :, 0] += H[:, 1:, :, 2] - H[:, :-1, :, 2]
    curl_H[:, :, 1:, 0] -= H[:, :, 1:, 1] - H[:, :, :-1, 1]

    curl_H[:, :, 1:, 1] += H[:, :, 1:, 0] - H[:, :, :-1, 0]
    curl_H[1:, :, :, 1] -= H[1:, :, :, 2] - H[:-1, :, :, 2]

    curl_H[1:, :, :, 2] += H[1:, :, :, 1] - H[:-1, :, :, 1]
    curl_H[:, 1:, :, 2] -= H[:, 1:, :, 0] - H[:, :-1, :, 0]

    return curl_H


## FDTD Grid Class
class Grid:
    from .visualization import visualize

    def __init__(
        self,
        shape: Tuple[Number, Number, Number],
        grid_spacing: float = 25e-9,
        permittivity: float = 1.0,
        permeability: float = 1.0,
        courant_number: float = None,
    ):
        """
        Args:
            shape: shape of the FDTD grid.
            grid_spacing = 50e-9: distance between the grid cells.
            permittivity = 1.0: the relative permittivity of the background.
            permeability = 1.0: the relative permeability of the background.
            courant_number = None: the courant number of the FDTD simulation.
                Defaults to the inverse of the square root of the number of
                dimensions > 1 (optimal value). The timestep of the simulation
                will be derived from this number using the CFL-condition.
        """
        # save the grid spacing
        self.grid_spacing = float(grid_spacing)

        # save grid shape as integers
        self.Nx, self.Ny, self.Nz = self._handle_tuple(shape)

        # dimension of the simulation:
        self.D = int(self.Nx > 1) + int(self.Ny > 1) + int(self.Nz > 1)

        # courant number of the simulation (optimal value)
        if courant_number is None:
            courant_number = (
                float(self.D) ** (-0.5) * 0.99
            )  # slight stability factor added
        self.courant_number = float(courant_number)

        # timestep of the simulation
        self.timestep = self.courant_number * self.grid_spacing / SPEED_LIGHT

        # save electric and magnetic field
        self.E = bd.zeros((self.Nx, self.Ny, self.Nz, 3))
        self.H = bd.zeros((self.Nx, self.Ny, self.Nz, 3))

        # save the inverse of the relative permittiviy and the relative permeability
        # these tensors can be anisotropic!
        self.inverse_permittivity = (
            bd.ones((self.Nx, self.Ny, self.Nz, 3)) / float(permittivity)
        )
        self.inverse_permeability = (
            bd.ones((self.Nx, self.Ny, self.Nz, 3)) / float(permeability)
        )

        # save current time index
        self.timesteps_passed = 0

        # dictionary containing the sources:
        self._sources = []

        # dictionary containing the boundaries
        self._boundaries = []

        # dictionary containing the detectors
        self._detectors = []

        # dictionary containing the objects in the grid
        self._objects = []

    def _handle_distance(self, distance: Number) -> int:
        """ transform a distance to an integer number of gridpoints """
        if not isinstance(distance, int):
            return int(float(distance) / self.grid_spacing + 0.5)
        return distance

    def _handle_time(self, time: Number) -> int:
        """ transform a time value to an integer number of timesteps """
        if not isinstance(time, int):
            return int(float(time) / self.timestep + 0.5)
        return time

    def _handle_tuple(
        self, shape: Tuple[Number, Number, Number]
    ) -> Tuple[int, int, int]:
        """ validate the grid shape and transform to a length-3 tuple of ints """
        if len(shape) != 3:
            raise ValueError(
                f"invalid grid shape {shape}\n"
                f"grid shape should be a 3D tuple containing floats or ints"
            )
        x, y, z = shape
        x = self._handle_distance(x)
        y = self._handle_distance(y)
        z = self._handle_distance(z)
        return x, y, z

    def _handle_slice(self, s: slice) -> slice:
        """ validate the slice and transform possibly float values to ints """
        start = s.start if not isinstance(s.start, float) else self._handle_distance(s.start)
        stop = s.stop if not isinstance(s.stop, float) else self._handle_distance(s.stop)
        step = s.step if not isinstance(s.step, float) else self._handle_distance(s.step)
        return slice(start, stop, step)

    def _handle_single_key(self, key):
        """ transform a single index key to a slice or list """
        try:
            len(key)
            return [self._handle_distance(k) for k in key]
        except TypeError:
            if isinstance(key, slice):
                return self._handle_slice(key)
            else:
                return [self._handle_distance(key)]
        return x

    @property
    def x(self) -> int:
        """ get the number of grid cells in the x-direction """
        return self.Nx * self.grid_spacing

    @property
    def y(self) -> int:
        """ get the number of grid cells in the y-direction """
        return self.Ny * self.grid_spacing

    @property
    def z(self) -> int:
        """ get the number of grid cells in the y-direction """
        return self.Nz * self.grid_spacing

    @property
    def shape(self) -> Tuple[int, int, int]:
        """ get the shape of the FDTD grid """
        return (self.Nx, self.Ny, self.Nz)

    @property
    def time_passed(self) -> float:
        """ get the total time passed """
        return self.timesteps_passed * self.timestep

    def run(self, total_time: Number, progress_bar: bool = True):
        """ run an FDTD simulation.

        Args:
            total_time: the total time for the simulation to run.
            progress_bar = True: choose to show a progress bar during
                simulation

        """
        if isinstance(total_time, float):
            total_time /= self.timestep
        time = range(0, int(total_time), 1)
        if progress_bar:
            time = tqdm(time)
        for _ in time:
            self.step()

    def step(self):
        """ do a single FDTD step by first updating the electric field and then
        updating the magnetic field
        """
        self.update_E()
        self.update_H()
        self.timesteps_passed += 1

    def update_E(self):
        """ update the electric field by using the curl of the magnetic field """

        # update boundaries: step 1
        for boundary in self._boundaries:
            boundary.update_phi_E()

        curl = curl_H(self.H)
        self.E += self.courant_number * self.inverse_permittivity * curl

        # update objects
        for obj in self._objects:
            obj.update_E(curl)

        # update boundaries: step 2
        for boundary in self._boundaries:
            boundary.update_E()

        # add sources to grid:
        for src in self._sources:
            src.update_E()

        # detect electric field
        for det in self._detectors:
            det.detect_E()

    def update_H(self):
        """ update the magnetic field by using the curl of the electric field """

        # update boundaries: step 1
        for boundary in self._boundaries:
            boundary.update_phi_H()

        curl = curl_E(self.E)
        self.H -= self.courant_number * self.inverse_permeability * curl

        # update objects
        for obj in self._objects:
            obj.update_H(curl)

        # update boundaries: step 2
        for boundary in self._boundaries:
            boundary.update_H()

        # add sources to grid:
        for src in self._sources:
            src.update_H()

        # detect electric field
        for det in self._detectors:
            det.detect_H()

    def reset(self):
        """ reset the grid by setting all fields to zero """
        self.H *= 0.0
        self.E *= 0.0
        self.timesteps_passed *= 0

    def add_source(self, name, source):
        """ add a source to the grid """
        source._register_grid(self)
        self._sources[name] = source

    def add_boundary(self, name, boundary):
        """ add a boundary to the grid """
        boundary._register_grid(self)
        self._boundaries[name] = boundary

    def add_detector(self, name, detector):
        """ add a detector to the grid """
        detector._register_grid(self)
        self._detectors[name] = detector

    def add_object(self, name, obj):
        """ add an object to the grid """
        obj._register_grid(self)
        self._objects[name] = obj

    def __setitem__(self, key, attr):
        if not isinstance(key, tuple):
            x, y, z = key, slice(None), slice(None)
        elif len(key) == 1:
            x, y, z = key[0], slice(None), slice(None)
        elif len(key) == 2:
            x, y, z = key[0], key[1], slice(None)
        elif len(key) == 3:
            x, y, z = key
        else:
            raise KeyError("maximum number of indices for the grid is 3")

        attr._register_grid(
            grid=self,
            x=self._handle_single_key(x),
            y=self._handle_single_key(y),
            z=self._handle_single_key(z),
        )

    def __str__(self):
        """ string representation of the grid

        lists all the components and their locations in the grid.
        """
        s = "Grid\n----\n\nsources:\n"
        for src in self._sources:
            s += "\t" + repr(src) + "\n"
            s += f"\t\t@x={src.x}, y={src.y}, z={src.z}\n"
        s = s + "\n\ndetectors:\n"
        for det in self._detectors:
            s += "\t" + repr(det) + "\n"
            s += f"\t\t@x={det.x}, y={det.y}, z={det.z}\n"
        s = s + "\n\nboundaries:\n"
        for bnd in self._boundaries:
            s += "\t" + repr(bnd) + "\n"
            s += f"\t\t@x={bnd.x}, y={bnd.y}, z={bnd.z}\n"
        s = s + "\n\nobjects:\n"
        for obj in self._objects:
            s += "\t" + repr(obj) + "\n"
            s += f"\t\t@x={obj.x}, y={obj.y}, z={obj.z}\n"

        return s
