"""Regression checks for BirdReport's current and legacy public formats."""

import csv
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from parse_birdreport_table import parse_birdreport_table
from birdreport_location_mapping import LocationMapper, load_location_mapper, parse_ranking_location

spec = importlib.util.spec_from_file_location(
    'city_reports', ROOT / '城市记录抓取' / 'fetch_city_reports.py'
)
city = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = city
spec.loader.exec_module(city)

OLD_HEADER = ['#', '鸟种编号', '中文名', '英文名称', '拉丁学名', '目', '科']
NEW_HEADER = ['#', '鸟种编号', '中文名', '拉丁学名', '英文名称', '目', '科', '记录次数']
OLD_ROW = ['1', '4148', '珠颈斑鸠', 'Spotted Dove', 'Spilopelia chinensis', '鸽形目', '鸠鸽科']
NEW_ROW = ['1', '4148', '珠颈斑鸠', 'Spilopelia chinensis', 'Spotted Dove', '鸽形目', '鸠鸽科', '3']
EXPECTED = {'chinese': '珠颈斑鸠', 'english': 'Spotted Dove', 'scientific': 'Spilopelia chinensis'}
QUERY = dict(province='北京市', city='', district='', pointname='',
             start='2026-10-01', end='2026-10-07', state='2',
             sort_by='serial_id', order_by='asc')


class TableCompatibilityTests(unittest.TestCase):
    def test_old_and_current_multiline_tables(self):
        for header, row in ((OLD_HEADER, OLD_ROW), (NEW_HEADER, NEW_ROW)):
            with self.subTest(header=header):
                self.assertEqual(parse_birdreport_table(['网站首页', *header, *row, 'Copyright']), [EXPECTED])

    def test_clipboard_rows_without_headers(self):
        for row in (OLD_ROW, NEW_ROW):
            with self.subTest(row=row):
                self.assertEqual(parse_birdreport_table(row), [EXPECTED])

    def test_tab_separated_rows_above_56(self):
        rows = ['\t'.join([str(n), *NEW_ROW[1:]]) for n in range(1, 101)]
        result = parse_birdreport_table(['\ufeff' + '\t'.join(NEW_HEADER), *rows])
        self.assertEqual(result, [EXPECTED] * 100)

    def test_column_order_follows_header(self):
        order = [0, 1, 4, 3, 2, 5, 6, 7]
        self.assertEqual(parse_birdreport_table([
            '\t'.join(NEW_HEADER[i] for i in order),
            '\t'.join(NEW_ROW[i] for i in order),
        ]), [EXPECTED])

    def test_empty_english_name_and_rare_chinese_characters(self):
        row = ['1', '4123', '小䴙䴘', 'Tachybaptus ruficollis', '', '䴙䴘目', '䴙䴘科', '3']
        self.assertEqual(parse_birdreport_table(['\t'.join(NEW_HEADER), '\t'.join(row)]), [
            {'chinese': '小䴙䴘', 'scientific': 'Tachybaptus ruficollis', 'english': ''}
        ])

    def test_repeated_headers_and_incomplete_row(self):
        self.assertEqual(parse_birdreport_table([
            *NEW_HEADER, *NEW_ROW, *NEW_HEADER, '2', '4123', '小䴙䴘'
        ]), [EXPECTED])


class CityReportCompatibilityTests(unittest.TestCase):
    def normalize(self, row):
        return city.normalize_row(row, query=QUERY, page=1, fetched_at='2026-10-14T00:00:00Z')

    def test_legacy_fields_take_precedence(self):
        row = {'province_name': '北京市', 'city_name': '北京市',
               'district_name': '朝阳区', 'point_name': '奥森北园',
               'address': '北京市北京市朝阳区奥森北园'}
        result = self.normalize(row)
        for key in ('province_name', 'city_name', 'district_name', 'point_name'):
            self.assertEqual(result[key], row[key])
        self.assertEqual(set(result), set(city.CSV_HEADERS))

    def test_current_address_restores_historical_location_fields(self):
        row = {'address': '北京市北京市朝阳区奥森北园河东', 'point_name': None}
        result = self.normalize(row)
        self.assertEqual(result['point_name'], '奥森北园河东')
        self.assertEqual(result['province_name'], '北京市')
        self.assertEqual(result['city_name'], '北京市')
        self.assertEqual(result['district_name'], '朝阳区')
        self.assertEqual(row['point_name'], None)

    def test_missing_address_stays_empty(self):
        self.assertEqual(self.normalize({})['point_name'], '')

    def test_ranking_keeps_current_addresses_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'reports.csv', Path(tmp) / 'ranking.csv'
            with source.open('w', encoding='utf-8', newline='') as fp:
                writer = csv.DictWriter(fp, fieldnames=city.CSV_HEADERS)
                writer.writeheader()
                for n, address in enumerate(('北京市北京市朝阳区奥森北园河东', '北京市北京市海淀区清河（奥森北园段）')):
                    writer.writerow(self.normalize({
                        'reportId': str(n), 'address': address, 'userid': str(n),
                        'taxoncount': 10, 'start_time': '2026-10-01 08:00',
                    }))
            subprocess.run([
                sys.executable, str(ROOT / '城市记录抓取' / 'build_point_period_stats.py'),
                '--input-csv', str(source), '--output-csv', str(target),
            ], check=True, capture_output=True, text=True)
            with target.open(encoding='utf-8-sig', newline='') as fp:
                points = {row['观鸟点名称'] for row in csv.DictReader(fp)}
            self.assertEqual(points, {
                '奥森北园河东', '清河（奥森北园段）'
            })

    def test_mixed_old_and_current_reports_aggregate_users_and_visits(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'reports.csv', Path(tmp) / 'ranking.csv'
            with source.open('w', encoding='utf-8', newline='') as fp:
                writer = csv.DictWriter(fp, fieldnames=city.CSV_HEADERS)
                writer.writeheader()
                legacy = dict(province_name='北京市', city_name='北京市', district_name='朝阳区',
                              point_name='奥森北园河东', userid='1', taxoncount=10, start_time='2026-10-01 08:00')
                writer.writerow(self.normalize(legacy))
                # Simulate CSVs produced by the initial full-address fallback.
                current = dict(point_name='北京市北京市朝阳区奥森北园河东', userid='1',
                               taxoncount=20, start_time='2026-10-02 08:00')
                writer.writerow({key: current.get(key, '') for key in city.CSV_HEADERS})
                current['userid'] = '2'
                writer.writerow({key: current.get(key, '') for key in city.CSV_HEADERS})
            subprocess.run([
                sys.executable, str(ROOT / '城市记录抓取' / 'build_point_period_stats.py'),
                '--input-csv', str(source), '--output-csv', str(target),
            ], check=True, capture_output=True, text=True)
            with target.open(encoding='utf-8-sig', newline='') as fp:
                rows = [row for row in csv.DictReader(fp) if row['时间段'] == '所有时段']
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['访问人数'], rows[0]['访问次数'], rows[0]['大概鸟种数']), ('2', '3', '20'))

    def test_ranking_separates_identical_point_names_in_different_districts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'reports.csv', Path(tmp) / 'ranking.csv'
            with source.open('w', encoding='utf-8', newline='') as fp:
                writer = csv.DictWriter(fp, fieldnames=city.CSV_HEADERS)
                writer.writeheader()
                for district in ('朝阳区', '海淀区'):
                    writer.writerow(self.normalize(dict(
                        province_name='北京市', city_name='北京市', district_name=district,
                        point_name='公园', userid='1', taxoncount=10, start_time='2026-10-01 08:00',
                    )))
            subprocess.run([
                sys.executable, str(ROOT / '城市记录抓取' / 'build_point_period_stats.py'),
                '--input-csv', str(source), '--output-csv', str(target),
            ], check=True, capture_output=True, text=True)
            with target.open(encoding='utf-8-sig', newline='') as fp:
                rows = [row for row in csv.DictReader(fp) if row['时间段'] == '所有时段']
            self.assertEqual({row['观鸟点名称'] for row in rows}, {
                '公园【北京市/北京市/朝阳区】', '公园【北京市/北京市/海淀区】'
            })
            self.assertTrue(all(row['访问次数'] == '1' for row in rows))


class LocationMappingTests(unittest.TestCase):
    def setUp(self):
        self.mapper = LocationMapper([
            ('北京市', '北京市', '朝阳区', '奥森北园河东'),
            ('北京市', '北京市', '海淀区', '公园'),
            ('广东省', '广州市', '白云区', '公园'),
        ])

    def test_exact_address_matches_and_new_points_use_known_prefix(self):
        mapped = self.mapper.resolve('北京市北京市朝阳区奥森北园河东')
        self.assertEqual(mapped['point_name'], '奥森北园河东')
        new = self.mapper.resolve('北京市北京市朝阳区奥森北园西侧')
        self.assertEqual((new['district_name'], new['point_name']), ('朝阳区', '奥森北园西侧'))

    def test_unknown_or_partial_address_is_preserved(self):
        for address in ('未知省未知市未知区公园', '北京市朝阳区公园', '北京市北京市朝阳区'):
            self.assertIsNone(self.mapper.resolve(address))
            self.assertEqual(self.mapper.normalize({'address': address})['point_name'], address)

    def test_equal_names_have_distinct_administrative_scopes(self):
        first = self.mapper.resolve('北京市北京市海淀区公园')
        second = self.mapper.resolve('广东省广州市白云区公园')
        self.assertEqual(first['point_name'], second['point_name'])
        self.assertNotEqual(first['city_name'], second['city_name'])

    def test_hotspot_search_terms_exclude_ranking_geographic_annotation(self):
        label = '公园【北京市/北京市/海淀区】'
        mapped = parse_ranking_location(label)
        self.assertEqual(mapped, dict(point_name='公园', province_name='北京市',
                                     city_name='北京市', district_name='海淀区'))
        for filename in ('apply_aug_dec_hotspots.py', 'suggest_aug_dec_hotspots.py'):
            spec = importlib.util.spec_from_file_location(filename[:-3], ROOT / '城市记录抓取' / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.normalize_name(label), '公园')
            if hasattr(module, 'choose_display_name'):
                self.assertEqual(module.choose_display_name(label), '公园')

    def test_ambiguous_exact_address_is_not_split_using_a_prefix(self):
        mapper = LocationMapper([('甲省', '乙市', '丙区', '丁点'), ('甲省', '乙市', '丙区丁', '点')])
        self.assertIsNone(mapper.resolve('甲省乙市丙区丁点'))

    def test_longest_known_administrative_prefix_wins(self):
        mapper = LocationMapper([('甲省', '乙市', '丙区', '点'), ('甲省', '乙市', '丙区丁', '点')])
        self.assertEqual(mapper.resolve('甲省乙市丙区丁新点')['district_name'], '丙区丁')

    def test_conflicting_legacy_administrative_field_is_preserved(self):
        row = {'address': '北京市北京市朝阳区奥森北园河东', 'province_name': '河北省'}
        result = self.mapper.normalize(row)
        self.assertEqual(result['province_name'], '河北省')
        self.assertEqual(result['point_name'], row['address'])

    def test_all_checked_in_historical_locations_round_trip(self):
        mapper = load_location_mapper()
        total = 0
        for path in sorted((ROOT / '城市记录抓取' / 'data').glob('*_报告索引.csv')):
            with path.open(encoding='utf-8-sig', newline='') as fp:
                for row in csv.DictReader(fp):
                    fields = ('province_name', 'city_name', 'district_name', 'point_name')
                    mapped = mapper.resolve(''.join(row[field] for field in fields))
                    self.assertEqual(mapped, {field: row[field].strip() for field in fields})
                    total += 1
        self.assertGreater(total, 0)


if __name__ == '__main__':
    unittest.main()
