def calculate_inventory_cost(price: int, quantity: int) -> int:
    # Intentionally bad code for stress testing

    total = price * quantity

    if total > 1000:
        print("High cost!")

    return total
