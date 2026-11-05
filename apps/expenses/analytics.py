"""Local category mapping and integer-cent chart aggregation."""
from collections import defaultdict
from datetime import date

CATEGORIES = ['Dining', 'Groceries', 'Shopping', 'Transport', 'Travel', 'Entertainment',
              'Housing', 'Utilities', 'Health', 'Personal care', 'Education', 'Fees', 'Other']
COLORS = ['#8f9bff', '#53d9be', '#f3b875', '#69b9ff', '#d19bff', '#f58cb5',
          '#e4d57c', '#83c9ac', '#a5b7ed', '#dda8a0', '#93c6cd', '#bfa477', '#798497']


def category_for(raw, description=''):
    value = (raw or '').upper().replace(' ', '_')
    mappings = [
        ('Groceries', ('GROCER', 'SUPERMARKET')),
        ('Dining', ('FOOD_AND_DRINK', 'RESTAURANT', 'COFFEE', 'DINING', 'FOOD')),
        ('Transport', ('TRANSPORT', 'GAS', 'AUTOMOTIVE', 'PARKING')),
        ('Travel', ('TRAVEL', 'AIRLINE', 'HOTEL')),
        ('Entertainment', ('ENTERTAINMENT', 'RECREATION')),
        ('Housing', ('RENT', 'MORTGAGE', 'HOME_IMPROVEMENT', 'HOUSING')),
        ('Utilities', ('UTILITIES', 'INTERNET', 'TELEPHONE', 'ELECTRIC')),
        ('Health', ('MEDICAL', 'HEALTH', 'PHARMACY')),
        ('Personal care', ('PERSONAL_CARE', 'GYM', 'FITNESS')),
        ('Education', ('EDUCATION', 'TUITION')),
        ('Fees', ('BANK_FEES', 'INTEREST', 'FEE')),
        ('Shopping', ('GENERAL_MERCHANDISE', 'SHOPPING', 'CLOTHING', 'ELECTRONICS')),
    ]
    for label, needles in mappings:
        if any(needle in value for needle in needles):
            return label
    # Only use conservative merchant rules when the provider category is absent.
    if value in ('', 'UNCATEGORIZED', 'OTHER'):
        text = description.casefold()
        for label, names in [('Groceries', ('whole foods', 'trader joe', 'kroger', 'heb ', 'h-e-b')),
                             ('Dining', ('starbucks', 'chipotle', 'doordash', 'ubereats')),
                             ('Transport', ('uber ', 'lyft', 'shell ', 'chevron')),
                             ('Entertainment', ('netflix', 'spotify', 'cinema'))]:
            if any(name in text for name in names):
                return label
    return 'Other'


def donut(rows):
    totals = defaultdict(int)
    for row in rows:
        if row['kind'] == 'expense' and not row['pending'] and row['currency'] == 'USD':
            totals[row['category_label']] += row['cents']
    total = sum(totals.values())
    offset = 0
    segments = []
    for label, cents in sorted(totals.items(), key=lambda pair: (-pair[1], pair[0])):
        percent = cents * 100 / total
        segments.append(dict(label=label, cents=cents, percent=percent, offset=offset,
                             color=COLORS[CATEGORIES.index(label)]))
        offset += percent
    return dict(total=total, segments=segments)


def months_ending(month, count=6):
    year, number = map(int, month.split('-'))
    index = year * 12 + number - 1
    return [f'{n // 12:04d}-{n % 12 + 1:02d}' for n in range(max(12, index-count+1), index+1)]


def analytics(rows, month, accounts, snapshots, selected='all'):
    visible = [row for row in rows if selected == 'all' or row['account_id'] == selected]
    monthly = [row for row in visible if row['day'].startswith(month)]
    posted = [row for row in monthly if not row['pending'] and row['currency'] == 'USD']
    income = sum(row['cents'] for row in posted if row['kind'] == 'income')
    gross = sum(row['cents'] for row in posted if row['kind'] == 'expense')
    refunds = sum(row['cents'] for row in posted if row['kind'] == 'refund')
    history = []
    for key in months_ending(month):
        cents = sum(row['cents'] for row in visible if row['day'].startswith(key)
                    and row['kind'] == 'expense' and not row['pending'] and row['currency'] == 'USD')
        history.append(dict(month=key, label=date.fromisoformat(key+'-01').strftime('%b'), cents=cents))
    maximum = max((point['cents'] for point in history), default=0) or 1
    for point in history:
        point['height'] = point['cents'] * 100 / maximum
    card_charts = []
    for account in accounts:
        if account['type'] == 'credit' and (selected == 'all' or selected == account['account_id']):
            chart = donut([row for row in monthly if row['account_id'] == account['account_id']])
            card_charts.append({**account, 'chart': chart})
    chosen_accounts = [a for a in accounts if (a['type'] == 'depository' if selected == 'all' else a['account_id'] == selected)]
    ids = {a['account_id'] for a in chosen_accounts}
    grouped = defaultdict(lambda: {'cents': 0, 'accounts': set()})
    for snapshot in snapshots:
        if snapshot['account_id'] in ids and snapshot['currency'] == 'USD' and snapshot['day'][:7] <= month:
            grouped[snapshot['day']]['cents'] += snapshot['balance_cents']
            grouped[snapshot['day']]['accounts'].add(snapshot['account_id'])
    balance = [{'day': key, 'cents': value['cents'], 'count': len(value['accounts'])} for key, value in sorted(grouped.items())][-180:]
    if balance:
        values = [p['cents'] for p in balance]
        minimum, maximum = min(values), max(values)
        padding = max((maximum-minimum)*.15, abs(maximum)*.02, 100)
        low, high = minimum-padding, maximum+padding
        first_day = date.fromisoformat(balance[0]['day'])
        span = (date.fromisoformat(balance[-1]['day']) - first_day).days
        for point in balance:
            elapsed = (date.fromisoformat(point['day']) - first_day).days
            point['x'] = 40 + (elapsed/span if span else .5)*620
            point['y'] = 160 - (point['cents']-low)/(high-low)*130
    is_credit = len(chosen_accounts) == 1 and chosen_accounts[0]['type'] == 'credit'
    return dict(items=monthly, income=income, spending=gross-refunds, net=income-gross+refunds,
                gross=gross, refunds=refunds, category_chart=donut(monthly), card_charts=card_charts,
                history=history, balance=balance,
                balance_title='Card balance history' if is_credit else ('Cash balance history' if selected == 'all' else 'Account balance history'),
                balance_points=' '.join(f"{p['x']:.2f},{p['y']:.2f}" for p in balance),
                balance_coverage_changed=len({tuple(sorted(grouped[p['day']]['accounts'])) for p in balance}) > 1)
