from __future__ import annotations

import unittest

from starter.ranges import CatalogRegistry, OrdinalRange, determine_range


class RangeTest(unittest.TestCase):
    def test_first_explicit_material_is_selected_deterministically(self) -> None:
        registry = CatalogRegistry(
            price_range=(1.0, 200.0),
            colors=frozenset(),
            materials=frozenset({"rayon", "spandex", "cotton"}),
            brands=frozenset(),
        )

        resolved = determine_range(
            "material", "95% Rayon, 5% Spandex", registry
        )

        self.assertIsInstance(resolved, OrdinalRange)
        self.assertEqual(resolved.selected, frozenset({"rayon"}))


if __name__ == "__main__":
    unittest.main()
