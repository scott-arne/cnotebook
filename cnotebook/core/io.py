"""Wire-format loader: parse HTTP-supplied structure strings into OE objects.

This is the input boundary for the HTTP API. It keeps all chemistry parsing in
the core (not the web layer) and never lets raw OpenEye errors escape: callers
get a typed MoleculeParseError instead.
"""

from __future__ import annotations

import base64

from openeye import oechem

from cnotebook.core.vocabulary import (
    BINARY_MOLECULE_FORMATS,
    MOLECULE_FORMATS,
)

# Text molecule formats handled by oemolistream, mapped to their OEFormat code.
_STREAM_FORMATS = {
    "sdf": oechem.OEFormat_SDF,
    "mol": oechem.OEFormat_MDL,
    "mol2": oechem.OEFormat_MOL2,
    "pdb": oechem.OEFormat_PDB,
    "oeb": oechem.OEFormat_OEB,
}


class MoleculeParseError(ValueError):
    """Raised when a wire-format input cannot be parsed.

    :param message: Human-readable reason.
    :param format: The declared input format that failed.
    """

    def __init__(self, message: str, fmt: str):
        super().__init__(message)
        self.format = fmt

    def __reduce__(self) -> tuple[type, tuple[str, str]]:
        # Default exception pickling replays ``self.args`` through ``__init__``,
        # but ``args`` holds only the message, so the required ``fmt`` would be
        # lost. Pin both fields so the error survives a process-pool boundary.
        return (self.__class__, (str(self), self.format))


def _decode(data: str, format: str, encoding: str) -> bytes | str:
    """Decode the raw input according to *encoding*, validating against *format*.

    :returns: ``bytes`` for binary formats, ``str`` for text formats.
    :raises MoleculeParseError: On encoding/format mismatch or bad base64.
    """
    is_binary = format in BINARY_MOLECULE_FORMATS
    if encoding == "base64":
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, TypeError) as exc:
            raise MoleculeParseError(f"Invalid base64 input: {exc}", format) from exc
        return raw if is_binary else raw.decode("utf-8", errors="replace")
    if encoding == "utf8":
        if is_binary:
            raise MoleculeParseError(
                f"Format '{format}' is binary and requires base64 encoding.", format
            )
        return data
    raise MoleculeParseError(f"Unknown encoding '{encoding}'.", format)


def load_molecules(data: str, format: str, encoding: str = "utf8") -> list[oechem.OEGraphMol]:
    """Parse every record in *data* into OE molecules.

    :param data: Structure text (or base64 for binary formats).
    :param format: One of :data:`cnotebook.core.vocabulary.MOLECULE_FORMATS` (not ``oedu``).
    :param encoding: ``"utf8"`` or ``"base64"``.
    :returns: A list of parsed molecules (possibly length 1).
    :raises MoleculeParseError: On unknown format, decode failure, or unreadable input.
    """
    if format not in MOLECULE_FORMATS or format == "oedu":
        raise MoleculeParseError(f"Unsupported molecule format '{format}'.", format)

    decoded = _decode(data, format, encoding)

    if format == "smiles":
        mol = oechem.OEGraphMol()
        if not oechem.OESmilesToMol(mol, str(decoded).strip()):
            raise MoleculeParseError("Could not parse SMILES.", format)
        return [mol]

    if format == "inchi":
        mol = oechem.OEGraphMol()
        if not oechem.OEInChIToMol(mol, str(decoded).strip()):
            raise MoleculeParseError("Could not parse InChI.", format)
        return [mol]

    oeformat = _STREAM_FORMATS[format]
    ims = oechem.oemolistream()
    ims.SetFormat(oeformat)
    if isinstance(decoded, bytes):
        if not ims.openstring(decoded):
            raise MoleculeParseError(f"Could not open {format} input stream.", format)
    else:
        if not ims.openstring(decoded.encode("utf-8")):
            raise MoleculeParseError(f"Could not open {format} input stream.", format)

    mols: list[oechem.OEGraphMol] = []
    for mol in ims.GetOEGraphMols():
        mols.append(oechem.OEGraphMol(mol))
    if not mols:
        raise MoleculeParseError(f"No molecules found in {format} input.", format)
    return mols


def load_molecule(data: str, format: str, encoding: str = "utf8") -> oechem.OEGraphMol:
    """Parse the FIRST record from *data*.

    :raises MoleculeParseError: As in :func:`load_molecules`.
    """
    return load_molecules(data, format, encoding)[0]


def load_design_unit(data: str, encoding: str = "base64") -> oechem.OEDesignUnit:
    """Parse an OpenEye design unit from base64-encoded ``.oedu`` bytes.

    Uses ``oeisstream`` (an in-memory string stream) with the 3-arg
    ``OEReadDesignUnit(ifs, du, type)`` overload — verified against the toolkit
    (``oeistream`` has no ``openstring``; the reader is filename- or
    ``oeisstream``-based).

    :raises MoleculeParseError: On decode failure or unreadable design unit.
    """
    raw = _decode(data, "oedu", encoding)
    if not isinstance(raw, bytes):  # pragma: no cover - oedu is always binary
        raise MoleculeParseError("Design units require base64 encoding.", "oedu")
    du = oechem.OEDesignUnit()
    ifs = oechem.oeisstream(raw)
    if not oechem.OEReadDesignUnit(ifs, du, oechem.OEDesignUnitFileType_OEDesignUnit):
        raise MoleculeParseError("Could not read design unit.", "oedu")
    return du
