from aiohttp import web
import random
import sqlite3
import time
import aiohttp_cors

active_games = {}

def init_db():
    conn = sqlite3.connect('casino.db', timeout=10)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY, balance INTEGER, last_bonus INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect('casino.db', timeout=10, check_same_thread=False)

def uid(v):
    try: return int(v)
    except: return None

# БАЛАНС
async def get_balance(request):
    user_id = uid(request.query.get('user_id'))
    if not user_id:
        return web.json_response({'error': 'no user_id'}, status=400)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute('INSERT INTO users (id,balance,last_bonus) VALUES (?,25000,0)', (user_id,))
        conn.commit(); balance = 25000
    else:
        balance = row[0]
    conn.close()
    return web.json_response({'balance': balance})

# БОНУС
BONUS_CD = 3600
BONUS_AMT = [500, 1000, 250, 5000, 100, 2000, 750, 3000]

async def claim_bonus(request):
    data = await request.json()
    user_id = uid(data.get('user_id'))
    if not user_id:
        return web.json_response({'error': 'no user_id'}, status=400)
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance,last_bonus FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute('INSERT INTO users (id,balance,last_bonus) VALUES (?,25000,0)', (user_id,))
        conn.commit(); row = (25000, 0)
    now = int(time.time()); last = row[1] or 0; diff = now - last
    if diff < BONUS_CD:
        remaining = BONUS_CD - diff; m,s = divmod(remaining,60)
        conn.close()
        return web.json_response({'error': f'Бонус доступен через {m}:{s:02d}'}, status=429)
    amount = random.choice(BONUS_AMT)
    sector_index = BONUS_AMT.index(amount)
    cur.execute('UPDATE users SET balance=balance+?,last_bonus=? WHERE id=?', (amount,now,user_id))
    conn.commit(); conn.close()
    return web.json_response({'message': f'🎉 Вы выиграли {amount} монет!', 'sector_index': sector_index, 'amount': amount})

# РУЛЕТКА
RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

async def play_roulette(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0)); b_type = data.get('type','')
    VALID_TYPES = ('red','black','green','even','odd','low','mid','high','low18','high18','row1','row2','row3')
    is_number_bet = b_type.startswith('number:')
    if not user_id or bet < 1 or (b_type not in VALID_TYPES and not is_number_bet):
        return web.json_response({'error': 'Неверные данные'}, status=400)
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row: conn.close(); return web.json_response({'error': 'Пользователь не найден'}, status=404)
    if row[0] < bet: conn.close(); return web.json_response({'error': 'Недостаточно монет!'}, status=400)
    num = random.randint(0,36)
    is_red = num in RED_NUMS
    is_even = num != 0 and num % 2 == 0
    # Подсчёт выигрыша
    win = 0
    if is_number_bet:
        try:
            chosen = int(b_type.split(':')[1])
            if num == chosen: win = bet * 36
        except: pass
    elif num == 0:
        win = bet * 35 if b_type == 'green' else 0
    elif b_type == 'red' and is_red: win = bet * 2
    elif b_type == 'black' and not is_red: win = bet * 2
    elif b_type == 'even' and is_even: win = bet * 2
    elif b_type == 'odd' and not is_even: win = bet * 2
    elif b_type == 'low18' and 1 <= num <= 18: win = bet * 2
    elif b_type == 'high18' and 19 <= num <= 36: win = bet * 2
    elif b_type == 'low' and 1 <= num <= 12: win = bet * 3
    elif b_type == 'mid' and 13 <= num <= 24: win = bet * 3
    elif b_type == 'high' and 25 <= num <= 36: win = bet * 3
    elif b_type == 'row1' and num in {3,6,9,12,15,18,21,24,27,30,33,36}: win = bet * 3
    elif b_type == 'row2' and num in {2,5,8,11,14,17,20,23,26,29,32,35}: win = bet * 3
    elif b_type == 'row3' and num in {1,4,7,10,13,16,19,22,25,28,31,34}: win = bet * 3
    cur.execute('UPDATE users SET balance=balance-?+? WHERE id=?', (bet,win,user_id))
    conn.commit(); conn.close()
    return web.json_response({'number': num, 'win': win})

# БЛЭКДЖЕК
def get_card(): return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
def calc(hand):
    s=sum(hand); a=hand.count(11)
    while s>21 and a: s-=10; a-=1
    return s

async def bj_start(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0))
    if not user_id or bet<1: return web.json_response({'error':'Неверные данные'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
    cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
    conn.commit();conn.close()
    p=[get_card(),get_card()]; d=[get_card(),get_card()]
    active_games[user_id]={'bet':bet,'p':p,'d':d}
    return web.json_response({'player_hand':p,'player_score':calc(p),'dealer_hand':[d[0]],'dealer_score':d[0],'status':'playing'})

async def bj_action(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); action=data.get('action')
    g=active_games.get(user_id)
    if not g: return web.json_response({'error':'Игра не найдена'},status=400)
    if action=='hit':
        g['p'].append(get_card())
        if calc(g['p'])>21: return await end_bj(user_id,'lose','💥 Перебор!')
    elif action=='stand':
        while calc(g['d'])<17: g['d'].append(get_card())
        ps,ds=calc(g['p']),calc(g['d'])
        if ds>21 or ps>ds: return await end_bj(user_id,'win','🏆 Ты выиграл!')
        elif ps<ds: return await end_bj(user_id,'lose','😔 Дилер выиграл.')
        else: return await end_bj(user_id,'draw','🤝 Ничья!')
    return web.json_response({'player_hand':g['p'],'player_score':calc(g['p']),'dealer_hand':[g['d'][0]],'dealer_score':g['d'][0],'status':'playing'})

async def end_bj(user_id, result, msg):
    g=active_games.pop(user_id); bet=g['bet']
    payout = bet*2 if result=='win' else (bet if result=='draw' else 0)
    if payout>0:
        conn=get_conn();cur=conn.cursor()
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(payout,user_id))
        conn.commit();conn.close()
    return web.json_response({'player_hand':g['p'],'player_score':calc(g['p']),'dealer_hand':g['d'],'dealer_score':calc(g['d']),'status':result,'message':msg})

# АВИАТОР — ставка
async def aviator_bet(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0))
    if not user_id or bet<1: return web.json_response({'error':'Неверные данные'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
    cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
    conn.commit();conn.close()
    return web.json_response({'ok':True})

# АВИАТОР — кэшаут
async def aviator_cashout(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0)); mul = float(data.get('multiplier',1.0))
    if not user_id or bet<1 or mul<1: return web.json_response({'error':'Неверные данные'},status=400)
    payout = int(bet * mul)
    conn=get_conn();cur=conn.cursor()
    cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(payout,user_id))
    conn.commit();conn.close()
    return web.json_response({'ok':True,'payout':payout})

# ОРЁЛ-РЕШКА
async def coin_flip(request):
    data = await request.json()
    user_id = uid(data.get('user_id'))
    bet = int(data.get('bet', 0))
    choice = data.get('choice', '')
    if not user_id or bet < 1 or choice not in ('heads', 'tails'):
        return web.json_response({'error': 'Неверные данные'}, status=400)
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row: conn.close(); return web.json_response({'error': 'Не найден'}, status=404)
    if row[0] < bet: conn.close(); return web.json_response({'error': 'Недостаточно монет!'}, status=400)
    result = random.choice(['heads', 'tails'])
    win = bet * 2 if result == choice else 0
    cur.execute('UPDATE users SET balance=balance-?+? WHERE id=?', (bet, win, user_id))
    conn.commit(); conn.close()
    return web.json_response({'result': result, 'win': win})

# КЕЙСЫ
CASES_FULL = {
    'starter': {'price':500, 'items':[
        {'v':-300,'ch':12,'e':'🪨','n':'Камень','r':'common'},
        {'v':-200,'ch':11,'e':'🍂','n':'Пыль','r':'common'},
        {'v':-150,'ch':10,'e':'🌫️','n':'Туман','r':'common'},
        {'v':-100,'ch':9, 'e':'🕸️','n':'Паутина','r':'common'},
        {'v':-50, 'ch':8, 'e':'🎃','n':'Тыква','r':'common'},
        {'v':-30, 'ch':6, 'e':'🥀','n':'Увядший','r':'common'},
        {'v':-20, 'ch':5, 'e':'🌑','n':'Пустота','r':'common'},
        {'v':50,  'ch':5, 'e':'🪙','n':'Монетка','r':'common'},
        {'v':100, 'ch':4, 'e':'💴','n':'Мелочь','r':'common'},
        {'v':200, 'ch':3, 'e':'🔑','n':'Ключик','r':'common'},
        {'v':300, 'ch':3, 'e':'🎫','n':'Билет','r':'common'},
        {'v':600, 'ch':5, 'e':'💰','n':'Кошелёк','r':'rare'},
        {'v':800, 'ch':4, 'e':'💵','n':'Купюра','r':'rare'},
        {'v':1200,'ch':4, 'e':'💳','n':'Карта','r':'rare'},
        {'v':2000,'ch':3, 'e':'💎','n':'Кристалл','r':'epic'},
        {'v':3000,'ch':2, 'e':'🔮','n':'Магия','r':'epic'},
        {'v':4000,'ch':1.5,'e':'🌟','n':'Звезда','r':'epic'},
        {'v':2500,'ch':2, 'e':'🏅','n':'Медаль','r':'epic'},
        {'v':7500,'ch':0.4,'e':'👑','n':'Корона','r':'legendary'},
        {'v':5000,'ch':0.6,'e':'⚡','n':'Молния','r':'epic'},
        {'v':15000,'ch':0.1,'e':'🏆','n':'Трофей','r':'legendary'},
    ]},
    'silver': {'price':1000, 'items':[
        {'v':-600,'ch':11,'e':'🪨','n':'Булыжник','r':'common'},
        {'v':-400,'ch':10,'e':'🍂','n':'Прах','r':'common'},
        {'v':-300,'ch':9, 'e':'🌫️','n':'Дым','r':'common'},
        {'v':-200,'ch':9, 'e':'🕸️','n':'Сеть','r':'common'},
        {'v':-100,'ch':8, 'e':'🎃','n':'Тыква гнилая','r':'common'},
        {'v':-60, 'ch':6, 'e':'🥀','n':'Сухоцвет','r':'common'},
        {'v':-40, 'ch':5, 'e':'🌑','n':'Тьма','r':'common'},
        {'v':100, 'ch':5, 'e':'🪙','n':'Серебрушка','r':'common'},
        {'v':250, 'ch':4, 'e':'💴','n':'Сторублёвка','r':'common'},
        {'v':500, 'ch':3, 'e':'🔑','n':'Серебряный ключ','r':'common'},
        {'v':700, 'ch':3, 'e':'🎫','n':'Талон','r':'common'},
        {'v':1300,'ch':5, 'e':'💰','n':'Портмоне','r':'rare'},
        {'v':1800,'ch':4, 'e':'💵','n':'Банкнота','r':'rare'},
        {'v':2500,'ch':3, 'e':'💳','n':'Золотая карта','r':'rare'},
        {'v':4000,'ch':3, 'e':'💎','n':'Алмаз','r':'epic'},
        {'v':6000,'ch':2, 'e':'🔮','n':'Оракул','r':'epic'},
        {'v':8000,'ch':1.5,'e':'🌟','n':'Суперзвезда','r':'epic'},
        {'v':5000,'ch':2, 'e':'🏅','n':'Серебряная медаль','r':'epic'},
        {'v':15000,'ch':0.4,'e':'👑','n':'Серебряная корона','r':'legendary'},
        {'v':10000,'ch':0.5,'e':'⚡','n':'Гром','r':'epic'},
        {'v':30000,'ch':0.1,'e':'🏆','n':'Серебряный кубок','r':'legendary'},
    ]},
    'gold': {'price':2500, 'items':[
        {'v':-1500,'ch':11,'e':'🪨','n':'Гравий','r':'common'},
        {'v':-1000,'ch':10,'e':'🍂','n':'Зола','r':'common'},
        {'v':-750, 'ch':9, 'e':'🌫️','n':'Смог','r':'common'},
        {'v':-500, 'ch':8, 'e':'🕸️','n':'Ловушка','r':'common'},
        {'v':-250, 'ch':8, 'e':'🎃','n':'Проклятие','r':'common'},
        {'v':-150, 'ch':6, 'e':'🥀','n':'Горечь','r':'common'},
        {'v':-100, 'ch':5, 'e':'🌑','n':'Чернота','r':'common'},
        {'v':300,  'ch':5, 'e':'🪙','n':'Золотник','r':'common'},
        {'v':700,  'ch':4, 'e':'💴','n':'Пятихатка','r':'common'},
        {'v':1500, 'ch':3, 'e':'🔑','n':'Золотой ключ','r':'common'},
        {'v':2000, 'ch':2, 'e':'🎫','n':'Ваучер','r':'common'},
        {'v':3500, 'ch':5, 'e':'💰','n':'Золотой сейф','r':'rare'},
        {'v':5000, 'ch':4, 'e':'💵','n':'Пачка купюр','r':'rare'},
        {'v':7500, 'ch':3, 'e':'💳','n':'Платиновая карта','r':'rare'},
        {'v':12000,'ch':3, 'e':'💎','n':'Бриллиант','r':'epic'},
        {'v':18000,'ch':2, 'e':'🔮','n':'Провидец','r':'epic'},
        {'v':25000,'ch':1, 'e':'🌟','n':'Галактика','r':'epic'},
        {'v':15000,'ch':1.5,'e':'🏅','n':'Золотая медаль','r':'epic'},
        {'v':40000,'ch':0.3,'e':'👑','n':'Золотая корона','r':'legendary'},
        {'v':30000,'ch':0.4,'e':'⚡','n':'Разряд','r':'epic'},
        {'v':75000,'ch':0.1,'e':'🏆','n':'Золотой кубок','r':'legendary'},
    ]},
    'diamond': {'price':5000, 'items':[
        {'v':-3000,'ch':11,'e':'🪨','n':'Уголь','r':'common'},
        {'v':-2000,'ch':10,'e':'🍂','n':'Осколки','r':'common'},
        {'v':-1500,'ch':9, 'e':'🌫️','n':'Туман войны','r':'common'},
        {'v':-1000,'ch':8, 'e':'🕸️','n':'Капкан','r':'common'},
        {'v':-500, 'ch':7, 'e':'🎃','n':'Злой рок','r':'common'},
        {'v':-300, 'ch':6, 'e':'🥀','n':'Разочарование','r':'common'},
        {'v':-200, 'ch':5, 'e':'🌑','n':'Провал','r':'common'},
        {'v':500,  'ch':5, 'e':'🪙','n':'Алмазник','r':'common'},
        {'v':1500, 'ch':4, 'e':'💴','n':'Тысячная','r':'common'},
        {'v':3000, 'ch':3, 'e':'🔑','n':'Алмазный ключ','r':'common'},
        {'v':4000, 'ch':2, 'e':'🎫','n':'Спецталон','r':'common'},
        {'v':7000, 'ch':5, 'e':'💰','n':'Бронированный сейф','r':'rare'},
        {'v':10000,'ch':4, 'e':'💵','n':'Кирпич денег','r':'rare'},
        {'v':15000,'ch':3, 'e':'💳','n':'Чёрная карта','r':'rare'},
        {'v':25000,'ch':3, 'e':'💎','n':'Идеальный алмаз','r':'epic'},
        {'v':40000,'ch':2, 'e':'🔮','n':'Всевидящий','r':'epic'},
        {'v':55000,'ch':1, 'e':'🌟','n':'Квазар','r':'epic'},
        {'v':35000,'ch':1.5,'e':'🏅','n':'Алмазная медаль','r':'epic'},
        {'v':90000,'ch':0.3,'e':'👑','n':'Алмазная корона','r':'legendary'},
        {'v':70000,'ch':0.4,'e':'⚡','n':'Шаровая молния','r':'epic'},
        {'v':150000,'ch':0.1,'e':'🏆','n':'Бриллиантовый кубок','r':'legendary'},
    ]},
    'vip': {'price':10000, 'items':[
        {'v':-6000,'ch':10,'e':'🪨','n':'Шлак','r':'common'},
        {'v':-4000,'ch':9, 'e':'🍂','n':'Хаос','r':'common'},
        {'v':-3000,'ch':9, 'e':'🌫️','n':'Пепел','r':'common'},
        {'v':-2000,'ch':8, 'e':'🕸️','n':'VIP-ловушка','r':'common'},
        {'v':-1000,'ch':7, 'e':'🎃','n':'Злой рок VIP','r':'common'},
        {'v':-600, 'ch':6, 'e':'🥀','n':'Фиаско','r':'common'},
        {'v':-400, 'ch':5, 'e':'🌑','n':'Чёрная дыра','r':'common'},
        {'v':1000, 'ch':4, 'e':'🪙','n':'VIP-монета','r':'common'},
        {'v':3000, 'ch':4, 'e':'💴','n':'Пятак','r':'common'},
        {'v':7000, 'ch':3, 'e':'🔑','n':'VIP-ключ','r':'common'},
        {'v':8000, 'ch':2, 'e':'🎫','n':'Пригласительный','r':'common'},
        {'v':15000,'ch':5, 'e':'💰','n':'VIP-сейф','r':'rare'},
        {'v':22000,'ch':4, 'e':'💵','n':'Чемодан наличных','r':'rare'},
        {'v':35000,'ch':3, 'e':'💳','n':'Карта мира','r':'rare'},
        {'v':60000,'ch':3, 'e':'💎','n':'VIP-алмаз','r':'epic'},
        {'v':90000,'ch':2, 'e':'🔮','n':'VIP-оракул','r':'epic'},
        {'v':130000,'ch':1,'e':'🌟','n':'Нейтронная звезда','r':'epic'},
        {'v':80000,'ch':1.5,'e':'🏅','n':'VIP-медаль','r':'epic'},
        {'v':200000,'ch':0.3,'e':'👑','n':'VIP-корона','r':'legendary'},
        {'v':150000,'ch':0.4,'e':'⚡','n':'Антиматерия','r':'epic'},
        {'v':400000,'ch':0.1,'e':'🏆','n':'Кубок чемпионов','r':'legendary'},
    ]},
    'legendary': {'price':25000, 'items':[
        {'v':-15000,'ch':10,'e':'🪨','n':'Метеорит','r':'common'},
        {'v':-10000,'ch':9, 'e':'🍂','n':'Судьба','r':'common'},
        {'v':-8000, 'ch':8, 'e':'🌫️','n':'Вакуум','r':'common'},
        {'v':-5000, 'ch':8, 'e':'🕸️','n':'Западня богов','r':'common'},
        {'v':-3000, 'ch':7, 'e':'🎃','n':'Проклятие богов','r':'common'},
        {'v':-1500, 'ch':6, 'e':'🥀','n':'Крах','r':'common'},
        {'v':-1000, 'ch':5, 'e':'🌑','n':'Горизонт событий','r':'common'},
        {'v':2500,  'ch':4, 'e':'🪙','n':'Легендарная монета','r':'common'},
        {'v':8000,  'ch':4, 'e':'💴','n':'Десятка тысяч','r':'common'},
        {'v':18000, 'ch':3, 'e':'🔑','n':'Мастер-ключ','r':'common'},
        {'v':20000, 'ch':2, 'e':'🎫','n':'VIP-пропуск','r':'common'},
        {'v':35000, 'ch':5, 'e':'💰','n':'Легендарный сейф','r':'rare'},
        {'v':55000, 'ch':4, 'e':'💵','n':'Состояние','r':'rare'},
        {'v':90000, 'ch':3, 'e':'💳','n':'Неограниченная карта','r':'rare'},
        {'v':150000,'ch':3, 'e':'💎','n':'Абсолютный алмаз','r':'epic'},
        {'v':225000,'ch':2, 'e':'🔮','n':'Пророчество','r':'epic'},
        {'v':350000,'ch':1, 'e':'🌟','n':'Пульсар','r':'epic'},
        {'v':200000,'ch':1.5,'e':'🏅','n':'Легендарная медаль','r':'epic'},
        {'v':500000,'ch':0.25,'e':'👑','n':'Корона богов','r':'legendary'},
        {'v':750000,'ch':0.15,'e':'⚡','n':'Сингулярность','r':'legendary'},
        {'v':1500000,'ch':0.1,'e':'🏆','n':'АБСОЛЮТ','r':'legendary'},
    ]},
}
# Для совместимости оставляем старый CASES_DATA
CASES_DATA = {k: {'price': v['price'], 'items': [(it['v'], it['ch']) for it in v['items']]} for k,v in CASES_FULL.items()}

def pick_prize_full(case_id):
    case = CASES_FULL.get(case_id)
    if not case: return None
    items = case['items']
    total = sum(it['ch'] for it in items)
    r = random.uniform(0, total)
    cum = 0
    for it in items:
        cum += it['ch']
        if r < cum:
            return it
    return items[-1]

async def open_case(request):
    data = await request.json()
    user_id = uid(data.get('user_id'))
    case_id = data.get('case_id','')
    count = max(1, min(int(data.get('count', 1)), 5))
    if not user_id or case_id not in CASES_FULL:
        return web.json_response({'error': 'Неверные данные'}, status=400)
    price = CASES_FULL[case_id]['price']
    total_cost = price * count
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row: conn.close(); return web.json_response({'error': 'Не найден'}, status=404)
    if row[0] < total_cost:
        conn.close()
        return web.json_response({'error': f'Недостаточно монет! Нужно {total_cost:,}'}, status=400)
    cur.execute('UPDATE users SET balance=balance-? WHERE id=?', (total_cost, user_id))
    conn.commit()
    prizes = []
    for _ in range(count):
        item = pick_prize_full(case_id)
        prize_value = item['v']
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?', (prize_value, user_id))
        conn.commit()
        prizes.append({
            'prize_value': prize_value,
            'name': item['n'],
            'emoji': item['e'],
            'rarity': item['r']
        })
    conn.close()
    return web.json_response({'ok': True, 'prizes': prizes})

# SWEET BONANZA SLOT
SB_SYMS = [
    {'e':'🍎','n':'Apple',  'w':180,'pays':{8:0.4,9:0.6,10:1,11:1.5,12:2,15:3,20:5,25:8}},
    {'e':'🍇','n':'Grape',  'w':160,'pays':{8:0.5,9:0.8,10:1.2,11:2,12:3,15:5,20:8,25:12}},
    {'e':'🍌','n':'Banana', 'w':150,'pays':{8:0.8,9:1.2,10:2,11:3,12:4,15:7,20:12,25:18}},
    {'e':'🍑','n':'Plum',   'w':140,'pays':{8:1,9:1.5,10:2.5,11:4,12:5,15:8,20:15,25:22}},
    {'e':'💎','n':'Diamond','w':60, 'pays':{8:2.5,9:4,10:6,11:9,12:13,15:20,20:35,25:50}},
    {'e':'❤️','n':'Heart',  'w':130,'pays':{8:1,9:1.5,10:2.5,11:4,12:5,15:8,20:15,25:22}},
    {'e':'🍬','n':'Candy',  'w':120,'pays':{8:1.5,9:2.5,10:4,11:6,12:8,15:15,20:25,25:35}},
    {'e':'🟦','n':'Blue',   'w':170,'pays':{8:0.4,9:0.6,10:1,11:1.5,12:2,15:3,20:5,25:8}},
    {'e':'🟩','n':'Green',  'w':165,'pays':{8:0.4,9:0.6,10:1,11:1.5,12:2,15:3,20:5,25:8}},
    {'e':'🟪','n':'Purple', 'w':110,'pays':{8:1.5,9:2.5,10:4,11:6,12:8,15:15,20:25,25:35}},
    {'e':'🍭','n':'Lolly',  'w':30, 'pays':{4:3,5:8,6:15,7:20}},  # scatter
]
SB_SCATTER_IDX=10
SB_MULT_VALS=[2,3,4,5,6,7,8,10,12,15,20,25,50,100]

def sb_rand_sym():
    total=sum(s['w'] for s in SB_SYMS)
    r=random.uniform(0,total); cum=0
    for i,s in enumerate(SB_SYMS):
        cum+=s['w']
        if r<cum: return i
    return 0

def sb_gen_grid():
    return [[sb_rand_sym() for _ in range(5)] for _ in range(6)]

def sb_find_clusters(grid):
    # Находим кластеры 8+ одинаковых символов в любом месте
    counts={}
    positions={}
    for col in range(6):
        for row in range(5):
            s=grid[col][row]
            if s!=SB_SCATTER_IDX:
                counts[s]=counts.get(s,0)+1
                if s not in positions: positions[s]=[]
                positions[s].append((col,row))
    clusters=[]
    for sym,cnt in counts.items():
        pays=SB_SYMS[sym]['pays']
        if sym==SB_SCATTER_IDX: continue
        thresholds=sorted([k for k in pays.keys() if k<=cnt],reverse=True)
        if thresholds:
            clusters.append({'sym':sym,'count':cnt,'pay_key':thresholds[0],'mult':pays[thresholds[0]],'cells':positions[sym]})
    return clusters

def sb_remove_winners(grid, clusters):
    to_remove=set()
    for c in clusters:
        for (col,row) in c['cells']: to_remove.add((col,row))
    # Удаляем и опускаем
    new_grid=[col[:] for col in grid]
    for col in range(6):
        col_syms=[new_grid[col][row] for row in range(5) if (col,row) not in to_remove]
        # Добавляем новые сверху
        while len(col_syms)<5: col_syms.insert(0,sb_rand_sym())
        new_grid[col]=col_syms
    return new_grid

async def slot_spin(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0))
    freespin = bool(data.get('freespin',False))
    if not user_id or bet < 100:
        return web.json_response({'error':'Мин. ставка 100'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if not freespin:
        if row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
        cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
        conn.commit()

    grid=sb_gen_grid()
    total_win=0; cascades=0; total_mult=1; all_wins=[]; all_mults={}

    # Каскады
    for cascade in range(10):
        clusters=sb_find_clusters(grid)
        if not clusters: break
        cascades+=1

        # Множители (во время фриспинов)
        cascade_mult=1
        if freespin and random.random()<0.35:
            # Добавляем 1-3 множителя
            num_m=random.randint(1,3)
            for _ in range(num_m):
                col=random.randint(0,5); row=random.randint(0,4)
                m=random.choice(SB_MULT_VALS)
                if col not in all_mults: all_mults[col]={}
                all_mults[col][row]=m
                cascade_mult+=m

        # Считаем выигрыш каскада
        cascade_win=sum(bet*c['mult'] for c in clusters)
        if freespin: cascade_win*=max(1,cascade_mult)
        total_win+=int(cascade_win)
        all_wins.extend(clusters)

        # Обновляем множитель
        if cascade>0: total_mult=cascade_mult if cascade_mult>1 else total_mult

        # Убираем выигравшие символы, новые падают
        grid=sb_remove_winners(grid,clusters)

    # Scatter = фриспины (4+ леденцов)
    scatter_count=sum(1 for col in range(6) for row in range(5) if grid[col][row]==SB_SCATTER_IDX)
    freespins_awarded=0
    if not freespin and scatter_count>=4:
        freespins_awarded=10+(scatter_count-4)*2

    if total_win>0:
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(total_win,user_id))
        conn.commit()
    conn.close()

    return web.json_response({
        'ok':True,'grid':grid,'wins':all_wins,'total_win':total_win,
        'total_mult':total_mult,'cascades':cascades,
        'multipliers':all_mults,'freespins':freespins_awarded
    })

# СТАКАНЧИКИ
async def cups_guess(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0)); won = bool(data.get('won',False))
    if not user_id or bet<1:
        return web.json_response({'error':'Неверные данные'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if not won and row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
    if won:
        win=bet*2
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(win,user_id))
    else:
        cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
        win=0
    conn.commit();conn.close()
    return web.json_response({'ok':True,'won':won,'win':win})

# APP
app = web.Application()
cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True,expose_headers="*",allow_headers="*",allow_methods="*")})
app.router.add_get('/get_balance', get_balance)
app.router.add_post('/play_roulette', play_roulette)
app.router.add_post('/bonus', claim_bonus)
app.router.add_post('/bj_start', bj_start)
app.router.add_post('/bj_action', bj_action)
app.router.add_post('/play_aviator_bet', aviator_bet)
app.router.add_post('/play_aviator_cashout', aviator_cashout)
app.router.add_post('/coin_flip', coin_flip)
app.router.add_post('/slot_spin', slot_spin)
app.router.add_post('/cups_guess', cups_guess)
app.router.add_post('/open_case', open_case)
for route in list(app.router.routes()): cors.add(route)

if __name__ == '__main__':
    init_db()
    print("✅ Сервер запущен на порту 4040")
    web.run_app(app, port=4040)
