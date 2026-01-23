import logging
from enum import Enum
from functools import wraps
from typing import Callable, Any, Literal, Generic, TypeVar
from collections.abc import Iterable
# noinspection PyPackageRequirements
from contextvars import ContextVar
from openeye import oechem, oedepict

log = logging.getLogger("cnotebook")


class _Deferred(Enum):
    """
    Sentinel to defer to global context
    This uses the approach suggested by Guido van Rossum
    https://github.com/python/typing/issues/236#issuecomment-227180301
    """
    value = 0


DEFERRED = _Deferred.value


########################################################################################################################
# Global Rendering Context
########################################################################################################################

T = TypeVar('T')


class DeferredValue(Generic[T]):
    """
    Value that can be deferred to the global CNotebook context
    """
    def __init__(self, name: str, value: T | _Deferred):
        self.name = name
        self._value = value
        self._initial_value = value

    def reset(self):
        """
        Reset this deferred value to the initial value (when the object was created)
        """
        self._value = self._initial_value

    @property
    def is_deferred(self) -> bool:
        """
        Check if the value is deferred to the global context
        :return: True if the value is deferred to the global
        """
        return self._value is DEFERRED

    def get(self) -> T:
        """
        If the value is DEFERRED then we defer to the local context
        :return: Value
        """
        if self.is_deferred:
            ctx = cnotebook_context.get()
            if not hasattr(ctx, self.name):
                raise AttributeError(f"Global context missing attribute '{self.name}'")
            return getattr(ctx, self.name)
        return self._value

    def set(self, value: T | _Deferred) -> None:
        """
        Set a value (we never set the global context)
        :param value: Value to set
        """
        self._value = value

    def __str__(self):
        return str(self.get())

    def __repr__(self):
        return repr(self.get())


class CNotebookContext:
    """
    Context in which to render OpenEye objects within IPython
    """
    # Supported image formats and their MIME types for rendering
    supported_mime_types = {
        'png': 'image/png',
        'svg': 'image/svg+xml'
    }

    def __init__(
            self,
            *,
            width: float | _Deferred = 0,
            height: float | _Deferred = 0,
            min_width: float | None | _Deferred = 200.0,
            min_height: float | None | _Deferred = 200.0,
            max_width: float | None | _Deferred = None,
            max_height: float | None | _Deferred = None,
            structure_scale: float | _Deferred = oedepict.OEScale_Default * 0.6,
            atom_label_font_scale: float | _Deferred = 1.0,
            title_font_scale: float | _Deferred = 1.0,
            image_format: str | _Deferred = "png",
            bond_width_scaling: bool | _Deferred = False,
            callbacks: Iterable[Callable[[oedepict.OE2DMolDisplay], None]] | None | _Deferred = None,
            scope: Literal["local", "global"] = "global",
            title: bool = True
    ):
        """
        Create the render context
        :param width: Image width (default of None means it is determined by the structure scale)
        :param height: Image height (default of None means it is determined by the structure scale)
        :param min_width: Minimum image width (prevents tiny images)
        :param min_height: Minimum image height (prevents tiny images)
        :param structure_scale: Structure scale
        :param title_font_scale: Font scaling (valid is 0.5 to 2.0)
        :param image_format: Image format
        :param bond_width_scaling: Bond width scaling
        """
        self._width = DeferredValue[float]("width", width)
        self._height = DeferredValue[float]("height", height)
        self._min_height = DeferredValue[float | None]("min_height", min_height)
        self._min_width = DeferredValue[float | None]("min_width", min_width)
        self._max_width = DeferredValue[float | None]("max_width", max_width)
        self._max_height = DeferredValue[float | None]("max_height", max_height)
        self._structure_scale = DeferredValue[float]("structure_scale", structure_scale)
        self._atom_label_font_scale = DeferredValue[float | None]("atom_label_font_scale", atom_label_font_scale)
        self._title_font_scale = DeferredValue[float]("title_font_scale", title_font_scale)
        self._image_format = DeferredValue[str]("image_format", image_format)
        self._bond_width_scaling = DeferredValue[bool]("bond_width_scaling", bond_width_scaling)
        self._title = DeferredValue[bool]("title", title)
        self._scope = scope

        # Set the callbacks (and do some type checking)
        if callbacks is None:
            self._callbacks = DeferredValue[list[Callable[[oedepict.OE2DMolDisplay], None]]](
                "callbacks",
                DEFERRED if scope == "local" else []
            )
        elif isinstance(callbacks, Iterable):
            self._callbacks = DeferredValue[list[Callable[[oedepict.OE2DMolDisplay], None]]](
                "callbacks",
                list(callbacks)
            )
        elif callbacks is DEFERRED:
            self._callbacks = DeferredValue[list[Callable[[oedepict.OE2DMolDisplay], None]]](
                "callbacks",
                DEFERRED
            )
        else:
            raise TypeError(f'Invalid type for display callbacks: {type(callbacks).__name__}')

    @property
    def width(self) -> float:
        return self._width.get()

    @width.setter
    def width(self, value: float) -> None:
        if self.max_width is not None and value > self.max_width:
            log.warning(f'Width exceeds max_width: {value} > {self.max_width}')

        self._width.set(value)

    @property
    def height(self) -> float:
        return self._height.get()

    @height.setter
    def height(self, value: float) -> None:
        if self.max_height is not None and value > self.max_height:
            log.warning(f'Height exceeds max_height: {value} > {self.max_height}')

        self._height.set(value)

    @property
    def min_width(self) -> float | None:
        return self._min_width.get()

    @min_width.setter
    def min_width(self, value: float | None) -> None:
        self._min_width.set(value)

    @property
    def max_width(self) -> float | None:
        return self._max_width.get()

    @max_width.setter
    def max_width(self, value: float | None):
        if value is not None and self.width > value:
            log.warning(f'Current width exceeds max_width: {self.width} > {value}')

        self._max_width.set(value)

    @property
    def max_height(self) -> float | None:
        return self._max_height.get()

    @max_height.setter
    def max_height(self, value: float | None):
        if value is not None and self.height > value:
            log.warning(f'Current height exceeds max_height: {self.height} > {value}')

        self._max_height.set(value)

    @property
    def min_height(self) -> float | None:
        return self._min_height.get()

    @min_height.setter
    def min_height(self, value: float | None) -> None:
        self._min_height.set(value)

    @property
    def structure_scale(self) -> float:
        return self._structure_scale.get()

    @structure_scale.setter
    def structure_scale(self, value: float) -> None:
        self._structure_scale.set(value)

    @property
    def atom_label_font_scale(self) -> float:
        return self._atom_label_font_scale.get()

    @atom_label_font_scale.setter
    def atom_label_font_scale(self, value: float) -> None:
        self._atom_label_font_scale.set(value)

    @property
    def title_font_scale(self) -> float:
        return self._title_font_scale.get()

    @title_font_scale.setter
    def title_font_scale(self, value: float) -> None:
        self._title_font_scale.set(value)

    @property
    def bond_width_scaling(self) -> bool:
        return self._bond_width_scaling.get()

    @bond_width_scaling.setter
    def bond_width_scaling(self, value: bool) -> None:
        self._bond_width_scaling.set(value)

    @property
    def image_format(self) -> str:
        return self._image_format.get()

    @image_format.setter
    def image_format(self, value: str) -> None:
        self._image_format.set(value)

    @property
    def scope(self) -> Literal["global", "local"]:
        return self._scope

    @property
    def callbacks(self) -> tuple[Callable[[oedepict.OE2DMolDisplay], None], ...]:
        # noinspection PyTypeChecker
        return tuple(self._callbacks.get())

    def reset_callbacks(self) -> None:
        self._callbacks.reset()

    @property
    def title(self) -> bool:
        return self._title.get()

    @title.setter
    def title(self, value: bool) -> None:
        self._title.set(value)

    @property
    def image_mime_type(self) -> str:
        mime_type = self.supported_mime_types.get(self.image_format, None)
        if mime_type is None:
            raise KeyError(f'No MIME type registered for image format {self.image_format}')
        return mime_type

    @property
    def display_options(self) -> oedepict.OE2DMolDisplayOptions:
        opts = oedepict.OE2DMolDisplayOptions()
        opts.SetHeight(self.height)
        opts.SetWidth(self.width)
        opts.SetScale(self.structure_scale)
        opts.SetTitleFontScale(self.title_font_scale)
        opts.SetBondWidthScaling(self.bond_width_scaling)
        opts.SetAtomLabelFontScale(self.atom_label_font_scale)

        if not self.title:
            opts.SetTitleLocation(oedepict.OETitleLocation_Hidden)

        return opts

    def add_callback(self, callback: Callable[[oedepict.OE2DMolDisplay], None]):
        """
        Add a callback that modifies an oedepict.OE2DMolDisplay to the current context
        :param callback: Callback to add
        """
        if self._callbacks.is_deferred:
            self._callbacks.set([])
        self._callbacks.get().append(callback)

    def create_molecule_display(
            self,
            mol: oechem.OEMolBase,
            min_height: int | None = None,
            min_width: int | None = None
    ) -> oedepict.OE2DMolDisplay:
        """
        Create a molecule display that enforces minimum image height and width
        :param mol: Molecule
        :param min_height: Minimum image height
        :param min_width: Minimum image width
        :return: Molecule display
        """
        disp = oedepict.OE2DMolDisplay(mol, self.display_options)

        # If the image was too small, and we're not enforcing a specific image size
        if ((self.width == 0.0 and self.min_width is not None and disp.GetWidth() < self.min_width) or
                (self.height == 0.0 and self.min_height is not None and disp.GetHeight() < self.min_height)):

            min_height = min_height or self.min_height
            min_width = min_width or self.min_width

            # Create a new display context
            new_ctx = self.copy()

            # If width was not enforced already, then enforce the minimum width
            if self.width == 0.0 and min_width is not None:
                new_ctx.width = min_width if disp.GetWidth() < self.min_width else 0.0

            # If height was not enforced already, then enforce the minimum height
            if self.height == 0.0 and min_height is not None:
                new_ctx.height = min_height if disp.GetHeight() < self.min_height else 0.0

            # Create the display object
            disp = oedepict.OE2DMolDisplay(mol, new_ctx.display_options)

        # We need to scale down the image if it exceeds the max_width or max_height
        if ((self.max_width is not None and disp.GetWidth() > self.max_width) or
                (self.max_height is not None and disp.GetHeight() > self.max_height)):

            # Create a new display context
            new_ctx = self.copy()

            # Set whatever parameter exceeded the maximum and let the other scale
            if self.max_width is not None and disp.GetWidth() > self.max_width:
                new_ctx.width = self.max_width
                new_ctx.height = 0

            elif self.max_height is not None and disp.GetHeight() > self.max_height:
                new_ctx.width = 0
                new_ctx.height = self.max_height

            new_ctx.structure_scale = oedepict.OEScale_AutoScale

            # Create the display object
            disp = oedepict.OE2DMolDisplay(mol, new_ctx.display_options)

            # TODO: Check the display again and see if we've exceeded max width or height again and potentially
            #       constrain both width and height

        return disp

    def reset(self) -> None:
        """
        Reset the rendering context to default values
        """
        self._width.reset()
        self._height.reset()
        self._min_width.reset()
        self._min_height.reset()
        self._max_width.reset()
        self._max_height.reset()
        self._structure_scale.reset()
        self._title_font_scale.reset()
        self._image_format.reset()
        self._bond_width_scaling.reset()
        self._title.reset()
        self._callbacks.reset()

    def copy(self) -> 'CNotebookContext':
        """
        Copy this object
        :return: Copy of the object
        """
        return CNotebookContext(
            width=self.width,
            height=self.height,
            min_width=self.min_width,
            min_height=self.min_height,
            max_width=self.max_width,
            max_height=self.max_height,
            structure_scale=self.structure_scale,
            title_font_scale=self.title_font_scale,
            title=self.title,
            image_format=self.image_format,
            bond_width_scaling=self.bond_width_scaling,
            callbacks=self.callbacks,
        )


########################################################################################################################
# !!!!!!!!! Global render context !!!!!!!!!
########################################################################################################################

# Create our global render context
cnotebook_context: ContextVar[CNotebookContext] = ContextVar("cnotebook_context", default=CNotebookContext())


########################################################################################################################
# Decorator to automatically pass global rendering context
########################################################################################################################

def pass_cnotebook_context(func):
    """
    Decorator that passes a copy of the current molecule render context
    :param func: Function to decorate
    :return: Decorated function
    """
    # TODO: Inspect func signature and check that it uses the ctx keyword
    @wraps(func)
    def call_with_render_context(*args, **kwargs):

        # If we happened to be called with a custom molecule render context
        if "ctx" in kwargs:
            ctx = kwargs.pop("ctx")

            if ctx is None:
                ctx = cnotebook_context.get().copy()

            # Other things are not OK
            elif not isinstance(ctx, CNotebookContext):
                raise TypeError("Received object of type type {} for OERenderContext (ctx) when calling {}".format(
                    type(ctx).__name__,
                    func.__name__
                ))
        else:
            ctx = cnotebook_context.get().copy()

        # Call the function
        return func(*args, **kwargs, ctx=ctx)
    return call_with_render_context


########################################################################################################################
# Local rendering context
########################################################################################################################

def create_local_context(
        width: float = DEFERRED,
        height: float = DEFERRED,
        min_width: float = DEFERRED,
        min_height: float = DEFERRED,
        max_width: float = DEFERRED,
        max_height: float = DEFERRED,
        structure_scale: int = DEFERRED,
        title_font_scale: float = DEFERRED,
        image_format: str = DEFERRED,
        bond_width_scaling: bool = DEFERRED,
        callbacks: Iterable[Callable[[oedepict.OE2DMolDisplay], None]] | None = DEFERRED
) -> CNotebookContext:
    return CNotebookContext(
        width=width,
        height=height,
        min_width=min_width,
        min_height=min_height,
        max_width=max_width,
        max_height=max_height,
        structure_scale=structure_scale,
        title_font_scale=title_font_scale,
        image_format=image_format,
        bond_width_scaling=bond_width_scaling,
        callbacks=callbacks,
        scope="local"
    )


def get_series_context(metadata: dict[Any, Any], save: bool = False) -> CNotebookContext:
    """
    Get the series context, else wrap the global context into a series context. This looks for the key "cnotebook" in
    the metadta.
    :param metadata: Series metadata
    :param save: Whether to save any new metadata object that we create
    :return: Series rendering context
    """
    ctx = metadata.get("cnotebook", create_local_context())

    # Make sure context is a valid object
    if not isinstance(ctx, CNotebookContext):
        log.warning(
            "Replacing unexpected object of type %s for metadata key 'cnotebook' with a CNotebookLocalContext",
            type(ctx).__name__
        )

        ctx = create_local_context()

    if save:
        metadata["cnotebook"] = ctx

    return ctx
