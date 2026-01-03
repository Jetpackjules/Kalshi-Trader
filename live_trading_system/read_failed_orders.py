try:
    with open('failed_orders_list.txt', 'r', encoding='utf-16') as f:
        print(f.read())
except:
    with open('failed_orders_list.txt', 'r', encoding='utf-8') as f:
        print(f.read())
