try:
    with open('canceled_orders.txt', 'r', encoding='utf-16') as f:
        print(f.read())
except:
    with open('canceled_orders.txt', 'r', encoding='utf-8') as f:
        print(f.read())
