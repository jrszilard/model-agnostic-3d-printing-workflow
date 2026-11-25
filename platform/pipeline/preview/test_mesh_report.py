"""Offline numeric projection tests, no CAD/mesh-file parser or browser."""
import copy
import math
import unittest
import xml.etree.ElementTree as ET

from mesh_report import mesh_svg, validate, VIEWS

POINTS = [[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 2]]
FACETS = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]


class MeshReportTests(unittest.TestCase):
    def test_passive_valid_svg_all_views(self):
        for view in VIEWS:
            svg = mesh_svg(POINTS, FACETS, view=view)
            root = ET.fromstring(svg)
            self.assertEqual(root.attrib['viewBox'], '0 0 360 240')
            self.assertIn('<polygon', svg)
            self.assertNotIn('script', svg)
            self.assertNotIn('href', svg)
            self.assertNotIn('foreignObject', svg)

    def test_pure_and_deterministic(self):
        points, facets = copy.deepcopy(POINTS), copy.deepcopy(FACETS)
        first = mesh_svg(points, facets, view='iso')
        self.assertEqual(first, mesh_svg(points, facets, view='iso'))
        self.assertEqual((points, facets), (POINTS, FACETS))

    def test_bounded_counts_and_triples(self):
        for points, facets in (([], FACETS), (POINTS, []), (POINTS*126, FACETS),
                               (POINTS, FACETS*126), ([[0, 1]], FACETS), (POINTS, [[0, 1]])):
            with self.subTest(points=len(points), facets=len(facets)), self.assertRaises(ValueError):
                validate(points, facets)

    def test_finite_plain_bounded_coordinates(self):
        for value in (True, '1', math.inf, -math.inf, math.nan, 1_000_001, 10**400):
            points = copy.deepcopy(POINTS)
            points[0][0] = value
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                validate(points, FACETS)

    def test_indices(self):
        for facet in ((0, 1, -1), (0, 1, 4), (0, 1, True), (0, 1, 2.0), (0, 1, 1)):
            with self.subTest(facet=facet), self.assertRaises(ValueError):
                validate(POINTS, [facet])

    def test_unknown_view_cannot_inject_markup(self):
        for view in ('<script>alert(1)</script>', 'front', None, []):
            with self.subTest(view=view), self.assertRaises(ValueError):
                mesh_svg(POINTS, FACETS, view=view)

    def test_degenerate_projection(self):
        with self.assertRaisesRegex(ValueError, 'degenerate projection'):
            mesh_svg([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 1, 2]], view='top')

    def test_coplanar_diagonal_not_drawn_as_feature_edge(self):
        root = ET.fromstring(mesh_svg([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]],
                                      [[0, 1, 2], [0, 2, 3]], view='top'))
        edges = root.findall("{http://www.w3.org/2000/svg}line[@stroke='#315065']")
        self.assertEqual(len(edges), 4)

    def test_no_visible_faces_not_a_blank_success(self):
        with self.assertRaisesRegex(ValueError, 'no visible triangles'):
            mesh_svg([[0, 0, 0], [2, 0, 0], [0, 2, 0]], [[0, 2, 1]], view='top')

    def test_camera_frame_and_depth(self):
        for right, down, depth in VIEWS.values():
            for axis in (right, down, depth):
                self.assertAlmostEqual(sum(x*x for x in axis), 1)
            self.assertAlmostEqual(sum(x*y for x, y in zip(right, down)), 0)
            self.assertAlmostEqual(sum(x*y for x, y in zip(right, depth)), 0)
        self.assertEqual(VIEWS['top'], ((1, 0, 0), (0, -1, 0), (0, 0, 1)))
        self.assertEqual(VIEWS['side'], ((0, 1, 0), (0, 0, -1), (1, 0, 0)))


if __name__ == '__main__':
    unittest.main()
