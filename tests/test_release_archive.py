"""Synthetic archive failures, runnable without PyBullet/Torch or training."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

SPEC = importlib.util.spec_from_file_location(
    'verify_release_archive', Path(__file__).resolve().parents[1]/'scripts/verify_release_archive.py')
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root/'study.zip'
        self.receipt = self.root/'study.receipt.json'
        self.sums = self.root/'SHA256SUMS'
        self.old = '/recorded/project'
        self.index = {
            'trainval': 'experiments/trainval.json', 'test': 'experiments/test.json',
            'potential': 'experiments/selected.json', 'freeze': 'experiments/freeze.json',
            'training': {'144': 'experiments/model144'},
            'evaluation': 'experiments/evaluation', 'report': 'deliverables/report',
            'delivery_validation': 'experiments/delivery', 'relocation_verification': 'experiments/relocation',
            'videos': ['deliverables/video.json'], 'demo': 'deliverables/video.mp4',
            'interpretation': 'deliverables/interpretation.md',
            'development_evidence': {'stage1': 'experiments/stage1'},
        }
        self.files = {name: b'inert fixture' for name in [
            self.index['trainval'], self.index['test'], self.index['potential'],
            'experiments/model144/best_model.zip', 'experiments/evaluation/episodes.json',
            'deliverables/report/report.pdf', 'experiments/delivery/status.json',
            'experiments/relocation/summary.json', 'deliverables/video.json',
            self.index['demo'], self.index['interpretation'], 'experiments/stage1/summary.json',
            'configs/protocol.json', 'src/inert.py']}
        self.files['src/inert.py'] = b'raise RuntimeError("archive code must never execute")\n'
        record = lambda name: {'path': self.old+'/'+name, 'sha256': sha(self.files[name])}
        self.freeze = {
            'status': 'frozen_before_test',
            'trainval_dataset': record(self.index['trainval']), 'test_dataset': record(self.index['test']),
            'potential_parameters_file': record(self.index['potential']),
            'protocol': record('configs/protocol.json'),
            'models': [{'seed': 144, **record('experiments/model144/best_model.zip')}],
            'source_file_hashes': {'src/inert.py': sha(self.files['src/inert.py'])},
            'audit': {'trainval': {'witnesses': []}, 'test_integrity': {'witnesses': [{'source': self.old+'/experiments/stage1', 'replay': self.old+'/experiments/evaluation'}]}, 'all_artifact_files': [record(self.index['trainval']), {
                'path': self.old+'/'+VERIFY.ASSET_PREFIX+'panda.urdf', 'sha256': '0'*64}]},
        }

        self.evaluation = {'freeze_manifest': self.index['freeze'], 'dataset': self.old+'/'+self.index['test'], 'dataset_sha256': self.freeze['test_dataset']['sha256'], 'models': deepcopy(self.freeze['models'])}

    def build(self, *, change_manifest=None, change_members=None, extra=None):
        files = deepcopy(self.files)
        files['study_index.json'] = encoded(self.index)
        files[self.index['evaluation']+'/config.json'] = encoded(self.evaluation)
        files[self.index['freeze']] = encoded(self.freeze)
        records = [{'path': k, 'archive_path': 'panda-posture/'+k,
                    'size_bytes': len(v), 'sha256': sha(v)} for k, v in files.items()]
        manifest = {'top_level_directory': 'panda-posture', 'git': {'commit': 'a'*40},
                    'file_count_excluding_manifest': len(records), 'files': records}
        if change_manifest:
            change_manifest(manifest)
        members = {'panda-posture/'+k: v for k, v in files.items()}
        members['panda-posture/PACKAGE_MANIFEST.json'] = encoded(manifest)
        if change_members:
            change_members(members)
        with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_STORED) as z:
            for name, raw in members.items():
                z.writestr(name, raw)
            if extra:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    z.writestr(*extra)
        self.receipt_data = {
            'zip_sha256': VERIFY.sha_file(self.archive), 'zip_size_bytes': self.archive.stat().st_size,
            'top_level_directory': 'panda-posture', 'package_manifest': 'panda-posture/PACKAGE_MANIFEST.json',
            'archive_file_count': len(members)+(1 if extra else 0), 'source_file_count': len(records),
            'index_sha256': sha(files['study_index.json']), 'git': {'commit': 'a'*40},
        }
        self.refresh_receipt()

    def refresh_receipt(self):
        self.receipt_data['zip_sha256'] = VERIFY.sha_file(self.archive)
        self.receipt_data['zip_size_bytes'] = self.archive.stat().st_size
        self.receipt.write_bytes(encoded(self.receipt_data))
        self.sums.write_text(f'{VERIFY.sha_file(self.archive)}  {self.archive.name}\n'
                             f'{VERIFY.sha_file(self.receipt)}  {self.receipt.name}\n')

    def run_check(self, docs=()):
        return VERIFY.verify_archive(self.archive, self.receipt, self.sums, docs)

    def test_valid_archive_does_not_extract_or_execute_and_marks_dependency_gap(self):
        self.build()
        before = set(self.root.iterdir())
        result = self.run_check()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['excluded_dependency_assets_not_checked'], 1)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_download_corruption(self):
        self.build()
        with self.archive.open('ab') as stream:
            stream.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Download SHA-256'):
            self.run_check()

    def test_receipt_corruption(self):
        self.build()
        self.receipt.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'Download SHA-256'):
            self.run_check()

    def test_manifest_sha_mismatch(self):
        self.build(change_manifest=lambda m: m['files'][0].update(sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'Member SHA-256'):
            self.run_check()

    def test_crc_corruption_even_with_refreshed_outer_checksums(self):
        self.build()
        with zipfile.ZipFile(self.archive) as z:
            info = z.getinfo('panda-posture/src/inert.py')
            offset = info.header_offset+30+len(info.filename.encode())+len(info.extra)
        with self.archive.open('r+b') as stream:
            stream.seek(offset)
            stream.write(b'X')
        self.refresh_receipt()
        with self.assertRaisesRegex(zipfile.BadZipFile, 'CRC'):
            self.run_check()

    def test_missing_member(self):
        self.build(change_members=lambda m: m.pop('panda-posture/src/inert.py'))
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.run_check()

    def test_duplicate_zip_member(self):
        self.build(extra=('panda-posture/src/inert.py', b'duplicate'))
        with self.assertRaisesRegex(ValueError, 'Duplicate ZIP'):
            self.run_check()

    def test_traversal_member(self):
        self.build(extra=('panda-posture/../escape', b'not extracted'))
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            self.run_check()

    def test_symlink_member(self):
        info = zipfile.ZipInfo('panda-posture/link')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.build(extra=(info, b'../../outside'))
        with self.assertRaisesRegex(ValueError, 'Non-regular'):
            self.run_check()

    def test_index_freeze_disagreement(self):
        self.index['test'] = self.index['trainval']
        self.build()
        with self.assertRaisesRegex(ValueError, 'Index/freeze mismatch'):
            self.run_check()

    def test_changed_frozen_artifact_hash(self):
        self.freeze['audit']['all_artifact_files'][0]['sha256'] = '0'*64
        self.build()
        with self.assertRaisesRegex(ValueError, 'Frozen hash mismatch'):
            self.run_check()

    def test_unexpected_missing_dependency_is_not_silently_skipped(self):
        self.freeze['audit']['all_artifact_files'][1]['path'] = self.old+'/.venv/unknown/model.bin'
        self.build()
        with self.assertRaisesRegex(ValueError, 'Missing indexed path'):
            self.run_check()

    def test_external_absolute_reference(self):
        self.freeze['protocol']['path'] = '/outside/protocol.json'
        self.build()
        with self.assertRaisesRegex(ValueError, 'outside recorded project root'):
            self.run_check()

    def test_frozen_source_changed(self):
        self.freeze['source_file_hashes']['src/inert.py'] = '0'*64
        self.build()
        with self.assertRaisesRegex(ValueError, 'Frozen source mismatch'):
            self.run_check()

    def test_missing_witness_directory(self):
        self.freeze['audit']['test_integrity']['witnesses'][0]['source'] = self.old+'/missing'
        self.build()
        with self.assertRaisesRegex(ValueError, 'Missing indexed path'):
            self.run_check()

    def test_evaluation_model_does_not_match_frozen_selection(self):
        self.evaluation['models'][0]['sha256'] = '0'*64
        self.build()
        with self.assertRaisesRegex(ValueError, 'Evaluation/freeze model mismatch'):
            self.run_check()

    def test_missing_readme_archive_path(self):
        self.build()
        doc = self.root/'README.md'
        doc.write_text('Evidence: `experiments/20261003T123456Z_missing/status.json`')
        with self.assertRaisesRegex(ValueError, 'Missing indexed path'):
            self.run_check([doc])


if __name__ == '__main__':
    unittest.main()
