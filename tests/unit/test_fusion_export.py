"""fusion_export.export_design against the SIMULATED Fusion API.

The fakes write files that look like each format (see tests/fakes/README.md),
so these tests check the add-in's own rules — file names, all-or-nothing
failures, linked-component detection, STL options — not Fusion's exports.
"""

import os
import tempfile
import unittest

import _paths
import adsk.fusion

import fusion_export as fe

ALL = ["f3d", "step", "iges", "sat", "stl"]


class ExportCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ftg_export_")
        self.addCleanup(_paths.force_rmtree, self.dir)

    def design(self, name="Bracket", bodies=("Body1",)):
        return adsk.fusion.Design(name, "urn:test", bodies=bodies)

    def export(self, design, formats, settings=None, base=None):
        return fe.export_design(design, self.dir, base or design.rootComponent.name, formats, settings or {})

    def names(self, result, fmt=None):
        paths = result.files if fmt is None else result.files_by_format.get(fmt, [])
        return sorted(os.path.basename(p) for p in paths)


class AllFormatsTests(ExportCase):
    def test_every_format_is_exported_and_checked(self):
        result = self.export(self.design(), ALL)
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(result.failures, [])
        self.assertEqual(self.names(result), ["Bracket.f3d", "Bracket.iges", "Bracket.sat", "Bracket.step", "Bracket.stl"])
        self.assertEqual(sorted(result.files_by_format), sorted(ALL))
        self.assertEqual(result.linked_components, [])

    def test_aliases_keep_their_extension_and_are_checked_as_their_format(self):
        result = self.export(self.design(), ["STP", "igs"])
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(self.names(result, "step"), ["Bracket.stp"])
        self.assertEqual(self.names(result, "iges"), ["Bracket.igs"])

    def test_unknown_formats_are_skipped_with_a_warning(self):
        result = self.export(self.design(), ["step", "obj"])
        self.assertTrue(result.ok, result.failures)
        self.assertIn("OBJ skipped", " ".join(result.warnings))

    def test_nothing_requested_is_not_ok(self):
        result = self.export(self.design(), [])
        self.assertFalse(result.ok)
        self.assertEqual(result.files, [])

    def test_stl_refinement_is_applied_and_an_old_step_protocol_setting_is_ignored(self):
        # The STEP AP203/AP214 option did nothing in Fusion and was removed
        # (audit BUG-03); a setting saved by an older version is ignored.
        design = self.design()
        self.export(design, ["step", "stl"], {"step": {"protocol": "AP203"}, "stl": {"meshRefinement": "low"}})
        by_format = {o.format: o for o in design.exportManager.executed}
        self.assertEqual(by_format["step"].applicationProtocol, "AP214")  # the fake's untouched default
        self.assertEqual(by_format["stl"].meshRefinement, adsk.fusion.MeshRefinementSettings.MeshRefinementLow)


class FailureTests(ExportCase):
    def test_each_failure_kind_is_reported_and_the_result_is_not_ok(self):
        cases = {
            "raise": "STEP export of Bracket.step failed: simulated step export error",
            "false": "Fusion reported that the STEP export of Bracket.step failed",
            "empty": "Bracket.step is empty",
            "missing": "Bracket.step was not created",
            "corrupt": "Bracket.step is not a STEP file",
        }
        for mode, expected in cases.items():
            with self.subTest(mode=mode):
                for name in os.listdir(self.dir):
                    os.remove(os.path.join(self.dir, name))
                design = self.design()
                design.exportManager.failures = {"step": mode}
                result = self.export(design, ["f3d", "step", "stl"])
                self.assertFalse(result.ok)
                self.assertEqual(len(result.failures), 1, result.failures)
                self.assertIn(expected, result.failures[0])
                # The other formats still exported, but the caller must not push them.
                self.assertIn("Bracket.f3d", self.names(result))

    def test_failure_while_preparing_options_is_reported(self):
        design = self.design()

        def broken(*_args):
            raise RuntimeError("no STEP translator")

        design.exportManager.createSTEPExportOptions = broken
        result = self.export(design, ["step"])
        self.assertFalse(result.ok)
        self.assertIn("couldn't be prepared: no STEP translator", result.failures[0])


class LinkedComponentTests(ExportCase):
    def test_linked_components_are_found_deduped_and_nested(self):
        design = self.design("Assembly")
        root = design.rootComponent
        bolt = adsk.fusion.Component("Bolt", ["Shank"])
        root.add_occurrence(bolt, linked=True)
        root.add_occurrence(bolt, linked=True)  # same component twice
        arm = root.add_occurrence(adsk.fusion.Component("Arm", ["Plate"]))
        arm.add_occurrence(adsk.fusion.Component("Motor"), linked=True)
        result = self.export(design, ["f3d"])
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(result.linked_components, ["Bolt", "Motor"])

    def test_an_unreadable_reference_is_a_warning_not_a_crash(self):
        design = self.design("Assembly")
        design.rootComponent.add_occurrence(adsk.fusion.Component("Ghost"), broken=True)
        result = self.export(design, ["f3d"])
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(result.linked_components, [])
        self.assertIn("Couldn't tell whether these components are linked from other designs: Ghost", result.warnings)

    def test_linked_components_only_matter_for_the_f3d_backup(self):
        design = self.design("Assembly")
        design.rootComponent.add_occurrence(adsk.fusion.Component("Bolt"), linked=True)
        self.assertEqual(self.export(design, ["step"]).linked_components, [])

    def linked_design(self):
        design = self.design("Assembly")
        design.rootComponent.add_occurrence(adsk.fusion.Component("Bolt"), linked=True)
        return design

    def test_a_design_with_linked_components_is_archived_as_f3z(self):
        # Fusion appends .f3d to an .f3z name (as reported); the name is corrected.
        result = self.export(self.linked_design(), ["f3d", "step"])
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(result.archive_format, "f3z")
        self.assertEqual([os.path.basename(p) for p in result.files], ["Assembly.f3z", "Assembly.step"])
        self.assertEqual(sorted(os.listdir(self.dir)), ["Assembly.f3z", "Assembly.step"])

    def test_an_f3z_written_with_its_own_name_is_used_as_is(self):
        design = self.linked_design()
        design.exportManager.f3z_behaviour = "exact"
        result = self.export(design, ["f3d"])
        self.assertTrue(result.ok, result.failures)
        self.assertEqual([os.path.basename(p) for p in result.files], ["Assembly.f3z"])

    def test_without_an_f3z_the_archive_falls_back_to_f3d(self):
        design = self.linked_design()
        design.exportManager.f3z_behaviour = "fail"
        result = self.export(design, ["f3d"])
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(result.archive_format, "f3d")
        self.assertEqual([os.path.basename(p) for p in result.files], ["Assembly.f3d"])
        self.assertTrue(any("couldn't write an .f3z archive" in w for w in result.warnings), result.warnings)

    def test_a_broken_f3z_is_a_failure_not_a_backup(self):
        design = self.linked_design()
        design.exportManager.failures["f3d"] = "corrupt"
        result = self.export(design, ["f3d"])
        self.assertFalse(result.ok)
        self.assertTrue(any("Assembly.f3z is not a Fusion archive" in f for f in result.failures), result.failures)

    def test_designs_without_linked_components_stay_f3d(self):
        result = self.export(self.design("Plain"), ["f3d"])
        self.assertEqual(result.archive_format, "f3d")
        self.assertEqual([os.path.basename(p) for p in result.files], ["Plain.f3d"])

    def test_question_and_history_note_wording(self):
        question = fe.linked_components_question(["A", "B", "C", "D", "E", "F", "G"])
        self.assertIn("uses 7 linked components (A, B, C, D, E, and 2 more)", question)
        self.assertIn("might not restore on its own", question)
        self.assertEqual(fe.linked_components_note(["Bolt"]),
                         "Contains 1 linked component (Bolt); this .f3d backup may not be self-contained.")
        f3z_question = fe.linked_components_question(["Bolt"], "f3z")
        self.assertIn("exported as an .f3z archive", f3z_question)
        self.assertIn("restoring one hasn't been verified yet", f3z_question)
        self.assertIn("might not restore on its own", f3z_question)


class StlTests(ExportCase):
    def test_millimetres_are_requested_when_fusion_supports_it(self):
        design = self.design()
        result = self.export(design, ["stl"])
        self.assertEqual(design.exportManager.executed[0].unitType, adsk.fusion.DistanceUnits.MillimeterDistanceUnits)
        self.assertNotIn(fe.STL_UNITS_WARNING, result.warnings)

    def test_older_fusion_without_unit_type_gets_a_warning_once(self):
        design = self.design(bodies=("A", "B"))
        design.exportManager.stl_unit_type_supported = False
        result = self.export(design, ["stl"], {"stl": {"files": fe.STL_PER_BODY}})
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(result.warnings.count(fe.STL_UNITS_WARNING), 1)
        self.assertFalse(hasattr(design.exportManager.executed[0], "unitType"))

    def test_profiles_without_the_files_setting_export_one_file(self):
        design = self.design(bodies=("A", "B"))
        result = self.export(design, ["stl"], {"stl": {"meshRefinement": "high"}})
        self.assertEqual(self.names(result), ["Bracket.stl"])
        self.assertIs(design.exportManager.executed[0].geometry, design.rootComponent)

    def test_one_file_per_body_names_nested_and_duplicate_bodies_deterministically(self):
        design = self.design("Robot", bodies=("Base", "base", "Hidden"))
        root = design.rootComponent
        root._bodies[2].isVisible = False
        wheel = adsk.fusion.Component("Wheel", ["Tyre"])
        left = root.add_occurrence(adsk.fusion.Component("Axle", ["Shaft"]))
        left.add_occurrence(wheel)
        left.add_occurrence(wheel)
        result = self.export(design, ["stl"], {"stl": {"files": fe.STL_PER_BODY}})
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(self.names(result), [
            "Robot - Axle 1 - Shaft.stl",
            "Robot - Axle 1 - Wheel 1 - Tyre.stl",
            "Robot - Axle 1 - Wheel 2 - Tyre.stl",
            "Robot - Base.stl",
            "Robot - base (2).stl",
        ])
        self.assertIn("1 hidden bodies were not exported as STL files.", result.warnings)
        # Same design, same names.
        again = fe.per_body_file_names("Robot", fe.stl_bodies(design)[0])
        self.assertEqual(sorted(again), self.names(result))

    def test_per_body_with_no_visible_bodies_fails(self):
        design = self.design(bodies=())
        result = self.export(design, ["stl"], {"stl": {"files": fe.STL_PER_BODY}})
        self.assertFalse(result.ok)
        self.assertIn("no visible bodies", result.failures[0])

    def test_a_failed_body_fails_the_whole_stl_export(self):
        design = self.design(bodies=("A", "B"))
        design.exportManager.failures = {"stl": "false"}
        result = self.export(design, ["stl"], {"stl": {"files": fe.STL_PER_BODY}})
        self.assertFalse(result.ok)
        self.assertEqual(len(result.failures), 2)
        self.assertEqual(result.files, [])


class NameTests(ExportCase):
    def test_unicode_reserved_and_unsafe_names_are_portable(self):
        cases = {
            "CON": "CON_.step",
            "Halterung für Motor": "Halterung für Motor.step",
            "Kaffé": "Kaffé.step",
            'Arm <v2>: "left"': "Arm _v2_ _left_.step",  # a run of unsafe characters is one "_"
            "../escape": "_escape.step",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                result = self.export(self.design(raw), ["step"], base=raw)
                self.assertTrue(result.ok, result.failures)
                self.assertEqual(self.names(result), [expected])
                self.assertEqual(os.path.dirname(result.files[0]), self.dir)

    def test_body_names_that_differ_only_in_case_never_overwrite_each_other(self):
        design = self.design("Part", bodies=("Arm", "ARM", "arm"))
        result = self.export(design, ["stl"], {"stl": {"files": fe.STL_PER_BODY}})
        self.assertTrue(result.ok, result.failures)
        self.assertEqual(self.names(result), ["Part - ARM (2).stl", "Part - Arm.stl", "Part - arm (3).stl"])
        self.assertEqual(len(os.listdir(self.dir)), 3)


if __name__ == "__main__":
    unittest.main()
