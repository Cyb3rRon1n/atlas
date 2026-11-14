from atlas.wiring.faceplate import physical_layout


def _ports(names):
    return {name: {"index": i, "up": i % 3 == 0, "speed": 1000} for i, name in enumerate(names, 1)}


def test_small_device_is_one_row_in_device_order():
    layout = physical_layout(_ports(["Port 1", "Port 2", "Port 3", "Port 4", "Port 5", "SFP+ 1", "SFP+ 2"]))
    assert layout["rows"] == 1 and layout["width"] == 7
    assert [p["label"] for p in layout["ports"]] == ["1", "2", "3", "4", "5", "S1", "S2"]
    assert [p["x"] for p in layout["ports"]] == [0, 1, 2, 3, 4, 5, 6]


def test_rack_switch_odd_top_even_bottom_blocks_and_extra_group():
    names = [f"gi{n}" for n in range(1, 29)] + [f"Po{n}" for n in range(1, 9)]
    layout = physical_layout(_ports(names))
    by = {p["name"]: p for p in layout["ports"]}
    assert layout["rows"] == 2 and layout["logical"] == sorted(f"Po{n}" for n in range(1, 9))
    assert (by["gi1"]["row"], by["gi1"]["x"]) == (0, 0) and (by["gi2"]["row"], by["gi2"]["x"]) == (1, 0)
    assert by["gi12"]["x"] == 5 and by["gi13"]["x"] == 6.5            # gap after 6 columns
    assert by["gi24"]["x"] == 11.5 and by["gi25"]["x"] > by["gi24"]["x"] + 1   # 25-28 are their own group
    assert by["gi25"]["row"] == 0 and by["gi26"]["row"] == 1 and by["gi27"]["x"] == by["gi25"]["x"] + 1
    assert layout["width"] == by["gi28"]["x"] + 1


def test_empty():
    assert physical_layout({}) == {"rows": 1, "width": 0, "ports": [], "logical": []}


def test_operator_rows_win_and_place_cages():
    ports = {name: {"index": i, "up": name == "gi13", "speed": 1000} for i, name in
             enumerate(["gi1", "gi13", "gi27", "Po1"], 1)}
    layout = physical_layout(ports, [["gi1", "-", "gi27", "sfp:gi27"], ["gi13"]])
    by = {(p["name"], p["cage"]): p for p in layout["ports"]}
    assert layout["rows"] == 2 and layout["width"] == 3.5
    assert (by[("gi13", False)]["row"], by[("gi13", False)]["x"], by[("gi13", False)]["up"]) == (1, 0, True)
    assert by[("gi27", False)]["x"] == 1.5 and by[("gi27", True)]["x"] == 2.5
    assert by[("gi27", True)]["label"] == "SFP 27"
    assert layout["logical"] == ["Po1"]
