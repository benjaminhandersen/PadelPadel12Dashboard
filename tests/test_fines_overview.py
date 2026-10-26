import unittest
from streamlit.testing.v1 import AppTest


class OverviewFiltersTest(unittest.TestCase):
    def test_type_filter_and_sort_order_update_all_totals(self):
        app = AppTest.from_string('''
from fines_overview import render_overview
render_overview([
 {'player':'Anna','reason':'Dobbeltfejl','quantity':4,'amount':40},
 {'player':'Bo','reason':'Dobbeltfejl','quantity':2,'amount':60},
 {'player':'Anna','reason':'Glemt bat','quantity':1,'amount':100}], ['Anna','Bo'], [])
''').run()
        app.selectbox[0].set_value('Dobbeltfejl').run()
        self.assertEqual(app.dataframe[0].value['Bøder (kr.)'].sum(), 100)
        self.assertEqual(app.dataframe[0].value.iloc[0]['Spiller'], 'Bo')
        app.selectbox[1].set_value('Flest bøder').run()
        self.assertEqual(app.dataframe[0].value.iloc[0]['Spiller'], 'Anna')
        self.assertEqual(app.dataframe[0].value['Antal'].sum(), 6)
        app.selectbox[0].set_value('Glemt bat').run()
        self.assertEqual(app.dataframe[0].value['Bøder (kr.)'].sum(), 100)
        self.assertFalse(app.exception)
