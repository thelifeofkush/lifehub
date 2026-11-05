import unittest

from apps.expenses.analytics import analytics, category_for


def row(day='2026-11-01', cents=1000, kind='expense', account='card-a', category='Dining', pending=False, currency='USD'):
    return dict(day=day, cents=cents, kind=kind, account_id=account, category_label=category, pending=pending, currency=currency)


class AnalyticsTests(unittest.TestCase):
    accounts = [dict(account_id='card-a',type='credit',label='Card A'),
                dict(account_id='card-b',type='credit',label='Card B'),
                dict(account_id='cash',type='depository',label='Checking')]

    def test_category_mapping_and_conservative_fallback(self):
        self.assertEqual(category_for('FOOD_AND_DRINK_GROCERIES'), 'Groceries')
        self.assertEqual(category_for('FOOD_AND_DRINK_RESTAURANTS'), 'Dining')
        self.assertEqual(category_for('GENERAL_MERCHANDISE_ONLINE_MARKETPLACES'), 'Shopping')
        self.assertEqual(category_for('Uncategorized', 'STARBUCKS 134'), 'Dining')
        self.assertEqual(category_for('Travel'), 'Travel')
        self.assertEqual(category_for('Uncategorized', 'Unknown merchant'), 'Other')

    def test_month_card_category_totals_and_transfer_exclusions(self):
        rows = [row(cents=2500), row(cents=4000,account='card-b',category='Groceries'),
                row(cents=1000,kind='refund'), row(cents=90000,kind='income'),
                row(cents=20000,kind='transfer'),row(cents=500,pending=True),
                row(cents=900,currency='EUR'),row(day='2026-10-10',cents=10000)]
        report=analytics(rows,'2026-11',self.accounts,[])
        self.assertEqual(report['category_chart']['total'],6500)
        self.assertEqual(report['spending'],5500)
        self.assertEqual(report['net'],84500)
        self.assertEqual(sum(s['cents'] for s in report['category_chart']['segments']),6500)
        self.assertAlmostEqual(sum(s['percent'] for s in report['category_chart']['segments']),100)
        self.assertEqual([card['chart']['total'] for card in report['card_charts']],[2500,4000])
        self.assertEqual(report['history'][-2]['cents'],10000)
        selected=analytics(rows,'2026-11',self.accounts,[],'card-b')
        self.assertEqual(selected['category_chart']['total'],4000)
        self.assertEqual(len(selected['card_charts']),1)
        self.assertEqual({r['account_id'] for r in selected['items']},{'card-b'})

    def test_balance_chart_separates_cash_from_debt_and_no_backfill(self):
        snapshots=[dict(account_id='cash',day='2026-11-04',balance_cents=10000,currency='USD'),
                   dict(account_id='cash',day='2026-11-05',balance_cents=12000,currency='USD'),
                   dict(account_id='card-a',day='2026-11-05',balance_cents=50000,currency='USD')]
        report=analytics([],'2026-11',self.accounts,snapshots)
        self.assertEqual([p['cents'] for p in report['balance']],[10000,12000])
        self.assertEqual(report['balance'][0]['day'],'2026-11-04')
        self.assertTrue(report['balance_points'])
        debt=analytics([],'2026-11',self.accounts,snapshots,'card-a')
        self.assertEqual(debt['balance_title'],'Card balance history')
        self.assertEqual(debt['balance'][0]['cents'],50000)
        self.assertEqual(analytics([],'2026-10',self.accounts,snapshots)['balance'],[])

    def test_zero_spending_and_year_boundary(self):
        report=analytics([],'2026-01',self.accounts,[])
        self.assertEqual(report['category_chart']['total'],0)
        self.assertEqual(report['history'][0]['month'],'2025-08')
        self.assertEqual(report['history'][-1]['month'],'2026-01')
        self.assertTrue(all(p['height']==0 for p in report['history']))
