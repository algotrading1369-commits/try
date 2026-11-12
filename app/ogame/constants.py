MISSION_ATTACK = 1
MISSION_TRANSPORT = 3
MISSION_DEPLOY = 4
MISSION_ACS_DEFEND = 5
MISSION_SPY = 6
MISSION_COLONIZE = 7
MISSION_RECYCLE = 8
MISSION_DESTROY = 9
MISSION_EXPEDITION = 15

DEST_PLANET = 1
DEST_DEBRIS = 2
DEST_MOON = 3
DEST_EXPEDITION = 1

COMPONENT_SUPPLIES = "supplies"
COMPONENT_FACILITIES = "facilities"
COMPONENT_RESEARCH = "research"
COMPONENT_SHIPYARD = "shipyard"
COMPONENT_DEFENSES = "defenses"

BUILDINGS = {
    1: {"name": "metal_mine", "component": "supplies", "metal": 60, "crystal": 15, "deuterium": 0, "factor": 1.5},
    2: {"name": "crystal_mine", "component": "supplies", "metal": 48, "crystal": 24, "deuterium": 0, "factor": 1.6},
    3: {"name": "deuterium_mine", "component": "supplies", "metal": 225, "crystal": 75, "deuterium": 0, "factor": 1.5},
    4: {"name": "solar_plant", "component": "supplies", "metal": 75, "crystal": 30, "deuterium": 0, "factor": 1.5},
    12: {"name": "fusion_plant", "component": "supplies", "metal": 900, "crystal": 360, "deuterium": 180, "factor": 1.8},
    22: {"name": "metal_storage", "component": "supplies", "metal": 2000, "crystal": 0, "deuterium": 0, "factor": 2},
    23: {"name": "crystal_storage", "component": "supplies", "metal": 2000, "crystal": 1000, "deuterium": 0, "factor": 2},
    24: {"name": "deuterium_storage", "component": "supplies", "metal": 2000, "crystal": 2000, "deuterium": 0, "factor": 2},
    14: {"name": "robotics_factory", "component": "facilities", "metal": 400, "crystal": 120, "deuterium": 200, "factor": 2},
    21: {"name": "shipyard", "component": "facilities", "metal": 400, "crystal": 200, "deuterium": 100, "factor": 2},
    31: {"name": "research_laboratory", "component": "facilities", "metal": 200, "crystal": 400, "deuterium": 200, "factor": 2},
    15: {"name": "nanite_factory", "component": "facilities", "metal": 1000000, "crystal": 500000, "deuterium": 100000, "factor": 2},
    44: {"name": "missile_silo", "component": "facilities", "metal": 20000, "crystal": 20000, "deuterium": 1000, "factor": 2},
    36: {"name": "repair_dock", "component": "facilities", "metal": 400, "crystal": 0, "deuterium": 300, "factor": 2},
    41: {"name": "moon_base", "component": "facilities", "metal": 20000, "crystal": 40000, "deuterium": 20000, "factor": 2},
    42: {"name": "sensor_phalanx", "component": "facilities", "metal": 20000, "crystal": 40000, "deuterium": 20000, "factor": 2},
    43: {"name": "jump_gate", "component": "facilities", "metal": 2000000, "crystal": 4000000, "deuterium": 2000000, "factor": 2},
}

RESEARCHES = {
    106: {"name": "espionage", "metal": 200, "crystal": 1000, "deuterium": 200, "factor": 2},
    108: {"name": "computer", "metal": 0, "crystal": 400, "deuterium": 600, "factor": 2},
    109: {"name": "weapons", "metal": 800, "crystal": 200, "deuterium": 0, "factor": 2},
    110: {"name": "shielding", "metal": 200, "crystal": 600, "deuterium": 0, "factor": 2},
    111: {"name": "armor", "metal": 1000, "crystal": 0, "deuterium": 0, "factor": 2},
    113: {"name": "energy", "metal": 0, "crystal": 800, "deuterium": 400, "factor": 2},
    115: {"name": "combustion_drive", "metal": 400, "crystal": 0, "deuterium": 600, "factor": 2},
    117: {"name": "impulse_drive", "metal": 2000, "crystal": 4000, "deuterium": 600, "factor": 2},
    118: {"name": "hyperspace_drive", "metal": 10000, "crystal": 20000, "deuterium": 6000, "factor": 2},
    120: {"name": "laser", "metal": 200, "crystal": 100, "deuterium": 0, "factor": 2},
    121: {"name": "ion", "metal": 1000, "crystal": 0, "deuterium": 300, "factor": 2},
    122: {"name": "plasma", "metal": 2000, "crystal": 4000, "deuterium": 1000, "factor": 2},
    123: {"name": "research_network", "metal": 240000, "crystal": 400000, "deuterium": 160000, "factor": 2},
    124: {"name": "astrophysics", "metal": 4000, "crystal": 8000, "deuterium": 4000, "factor": 1.75},
    199: {"name": "graviton", "metal": 0, "crystal": 0, "deuterium": 0, "factor": 3},
}

SHIPS = {
    202: {"name": "small_transporter", "metal": 2000, "crystal": 2000, "deuterium": 0, "cargo": 5000, "speed": 5000, "fuel": 10},
    203: {"name": "large_transporter", "metal": 6000, "crystal": 6000, "deuterium": 0, "cargo": 25000, "speed": 7500, "fuel": 50},
    204: {"name": "light_fighter", "metal": 3000, "crystal": 1000, "deuterium": 0, "cargo": 50, "speed": 12500, "fuel": 20},
    205: {"name": "heavy_fighter", "metal": 6000, "crystal": 4000, "deuterium": 0, "cargo": 100, "speed": 10000, "fuel": 75},
    206: {"name": "cruiser", "metal": 20000, "crystal": 7000, "deuterium": 2000, "cargo": 800, "speed": 15000, "fuel": 300},
    207: {"name": "battleship", "metal": 45000, "crystal": 15000, "deuterium": 0, "cargo": 1500, "speed": 10000, "fuel": 500},
    208: {"name": "colony_ship", "metal": 10000, "crystal": 20000, "deuterium": 10000, "cargo": 7500, "speed": 2500, "fuel": 1000},
    209: {"name": "recycler", "metal": 10000, "crystal": 6000, "deuterium": 2000, "cargo": 20000, "speed": 2000, "fuel": 300},
    210: {"name": "espionage_probe", "metal": 0, "crystal": 1000, "deuterium": 0, "cargo": 5, "speed": 100000000, "fuel": 1},
    211: {"name": "bomber", "metal": 50000, "crystal": 25000, "deuterium": 15000, "cargo": 500, "speed": 4000, "fuel": 1000},
    213: {"name": "destroyer", "metal": 60000, "crystal": 50000, "deuterium": 15000, "cargo": 2000, "speed": 5000, "fuel": 1000},
    214: {"name": "deathstar", "metal": 5000000, "crystal": 4000000, "deuterium": 1000000, "cargo": 1000000, "speed": 100, "fuel": 1},
    215: {"name": "interceptor", "metal": 30000, "crystal": 40000, "deuterium": 15000, "cargo": 750, "speed": 10000, "fuel": 250},
    218: {"name": "reaper", "metal": 85000, "crystal": 61000, "deuterium": 15000, "cargo": 10000, "speed": 7000, "fuel": 1100},
    219: {"name": "pathfinder", "metal": 8000, "crystal": 15000, "deuterium": 8000, "cargo": 12000, "speed": 12000, "fuel": 700},
    212: {"name": "solar_satellite", "metal": 0, "crystal": 2000, "deuterium": 500, "cargo": 0, "speed": 0, "fuel": 0},
    217: {"name": "crawler", "metal": 2000, "crystal": 2000, "deuterium": 1000, "cargo": 0, "speed": 0, "fuel": 0},
}

DEFENSES = {
    401: {"name": "rocket_launcher", "metal": 2000, "crystal": 0, "deuterium": 0},
    402: {"name": "light_laser", "metal": 1500, "crystal": 3000, "deuterium": 0},
    403: {"name": "heavy_laser", "metal": 6000, "crystal": 2000, "deuterium": 0},
    404: {"name": "gauss_cannon", "metal": 20000, "crystal": 15000, "deuterium": 2000},
    405: {"name": "ion_cannon", "metal": 2000, "crystal": 6000, "deuterium": 0},
    406: {"name": "plasma_cannon", "metal": 50000, "crystal": 50000, "deuterium": 30000},
    407: {"name": "small_shield_dome", "metal": 10000, "crystal": 10000, "deuterium": 0},
    408: {"name": "large_shield_dome", "metal": 50000, "crystal": 50000, "deuterium": 0},
    502: {"name": "anti_ballistic_missile", "metal": 8000, "crystal": 0, "deuterium": 2000},
    503: {"name": "interplanetary_missile", "metal": 12500, "crystal": 2500, "deuterium": 10000},
}

TECH_NAMES = {}
for _d in (BUILDINGS, RESEARCHES, SHIPS, DEFENSES):
    for _id, _info in _d.items():
        TECH_NAMES[_id] = _info["name"]

MISSION_NAMES = {
    1: "Ataque",
    3: "Transporte",
    4: "Despliegue",
    5: "Defensa ACS",
    6: "Espionaje",
    7: "Colonizar",
    8: "Reciclaje",
    9: "Destruir luna",
    15: "Expedición",
    16: "ACS Ataque",
}


def building_cost(tech_id: int, level: int):
    info = BUILDINGS.get(tech_id) or RESEARCHES.get(tech_id)
    factor = info["factor"]
    return (
        int(info["metal"] * factor ** (level - 1)),
        int(info["crystal"] * factor ** (level - 1)),
        int(info["deuterium"] * factor ** (level - 1)),
    )


def unit_cost(tech_id: int, amount: int = 1):
    info = SHIPS.get(tech_id) or DEFENSES.get(tech_id)
    return (
        info["metal"] * amount,
        info["crystal"] * amount,
        info["deuterium"] * amount,
    )
