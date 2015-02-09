"""

Validate credit card numbers

http://en.wikipedia.org/wiki/Luhn_algorithm

"""


from __future__ import unicode_literals
from __future__ import print_function
from .compat import text_type


def checksum(card_number):
    """Calculate the luhn checksum"""
    def digits_of(n):
        return [int(d) for d in text_type(n)]
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    return checksum % 10


def validate(card_number):
    """Validate a card number"""
    card_number = ''.join(c for c in text_type(card_number) if c.isdigit())
    return checksum(card_number) == 0


if __name__ == "__main__":
    print(validate("4111 1111 1111 1111"))  # True
    print(validate("5500 0000 0000 0004"))  # True
    print(validate("6011 0000 0000 0004"))  # True
    print(validate("3088 0000 0000 0009"))  # True
    print(validate("5500 0000 0000 0005"))  # False
