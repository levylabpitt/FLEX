"""Instrument drivers by vendor; modules load only when CATALOG resolves them."""

from flex_drivers.levylab import CATALOG as _LEVYLAB_CATALOG

CATALOG: dict[str, str] = {
    "srs.sr7270": "flex_drivers.srs.sr7270:SR7270",
    "colby.pdl": "flex_drivers.colby.pdl:ColbyPDL",
    "rotrics.dexarm": "flex_drivers.rotrics.dexarm:DexArm",
    "aseq.spectrometer": "flex_drivers.aseq.aseq:ASEQSpectrometer",
    "newport.conex_agp": "flex_drivers.newport.conex_agp:ConexAGP",
    "newport.nf8742": "flex_drivers.newport.nf8742:NF8742",
    "ophir.nova": "flex_drivers.ophir.nova:OphirNova",
    "sphere.dscan": "flex_drivers.sphere.dscan:DScan",
    **_LEVYLAB_CATALOG,
}

__all__ = ["CATALOG"]
