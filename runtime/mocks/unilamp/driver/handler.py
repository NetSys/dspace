import os

import on
from util import put, first_attr, first_type

"""Universal lamp translates power and brightness 
to vendor specific lamps."""

# converters
converters = {
    "mock.digi.dev/v1/lamps": {
        "power": {
            "from": lambda x: x,
            "to": lambda x: x,
        },
        "brightness": {
            "from": lambda x: x,
            "to": lambda x: x,
        }
    },
    "mock.digi.dev/v1/colorlamps": {
        "power": {
            "from": lambda x: "on" if x == 1 else "off",
            "to": lambda x: 1 if x == "on" else 0,
        },
        "brightness": {
            "from": lambda x: x / 255,
            "to": lambda x: x * 255,
        },
        "hue": {
            "from": lambda: -1,
            "to": lambda: -1,
        },
        "saturation": {
            "from": lambda: -1,
            "to": lambda: -1,
        }
    },
}


# validation
@on.mount
def h(lamp_types):
    count = 0
    for typ, lamps in lamp_types.items():
        count += len(lamps)
    assert count <= 1, \
        f"more than one lamp is mounted: " \
        f"{count}"


# intent back-prop
@on.mount
def h(parent, bp):
    ul = parent

    for _, child_path, old, new in bp:
        typ, attr = child_path[2], child_path[-2]

        assert typ in converters, typ

        put(path=f"control.{attr}.intent",
            src=new, target=ul,
            transform=converters[typ][attr]["from"])


# status
@on.mount("lamps")
def h(lp, ul, typ):
    lp = first_attr("spec", lp)

    assert typ in converters, typ

    put(f"control.power.status", lp, ul,
        transform=converters[typ]["power"]["from"])

    put(f"control.brightness.status", lp, ul,
        transform=converters[typ]["brightness"]["from"])


@on.mount("colorlamps")
def h(lp, ul, typ):
    lp = first_attr("spec", lp)

    assert typ in converters, typ

    put(f"control.power.status", lp, ul,
        transform=converters[typ]["power"]["from"])

    put(f"control.brightness.status", lp, ul,
        transform=converters[typ]["brightness"]["from"])


# intent
@on.mount
@on.control
def h(parent, child):
    ul, lp = parent, first_attr("spec", child)
    if lp is None:
        return

    typ = first_type(child)
    assert typ in converters, typ

    put(f"control.power.intent", ul, lp,
        transform=converters[typ]["power"]["to"])

    put(f"control.brightness.intent", ul, lp,
        transform=converters[typ]["brightness"]["to"])