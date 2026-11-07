import tokenize
import io

def tokenize_repair(code_str: str) -> str:
    tokens = list(tokenize.generate_tokens(io.StringIO(code_str).readline))
    new_tokens = []
    
    for i, tok in enumerate(tokens):
        # Implicit multiplication insertions before appending current token
        if i > 0:
            prev = tokens[i-1]
            if prev.type == tokenize.NUMBER and tok.type == tokenize.NAME:
                new_tokens.append((tokenize.OP, '*'))
            elif prev.type == tokenize.NUMBER and tok.type == tokenize.OP and tok.string == '(':
                new_tokens.append((tokenize.OP, '*'))
            elif prev.type == tokenize.OP and prev.string == ')' and tok.type in (tokenize.NAME, tokenize.NUMBER):
                new_tokens.append((tokenize.OP, '*'))
            elif prev.type == tokenize.OP and prev.string == ')' and tok.type == tokenize.OP and tok.string == '(':
                new_tokens.append((tokenize.OP, '*'))

        # 1. Caret ^ operator to **
        if tok.type == tokenize.OP and tok.string == '^':
            new_tokens.append((tokenize.OP, '**'))
            continue

        # 2. Attribute / symbol hallucinations on NAME tokens
        if tok.type == tokenize.NAME and tok.string == 'Degree':
            new_tokens.append((tokenize.OP, '('))
            new_tokens.append((tokenize.NAME, 'sp'))
            new_tokens.append((tokenize.OP, '.'))
            new_tokens.append((tokenize.NAME, 'pi'))
            new_tokens.append((tokenize.OP, '/'))
            new_tokens.append((tokenize.NUMBER, '180'))
            new_tokens.append((tokenize.OP, ')'))
            continue
        elif tok.type == tokenize.NAME and tok.string == 'infinity':
            new_tokens.append((tokenize.NAME, 'oo'))
            continue

        new_tokens.append((tok.type, tok.string))

    return tokenize.untokenize(new_tokens)

sample = 'expr = 2x^2 + 5x - 3(a + b)\nmsg = "2x^2 in string must stay 2x^2"\nprint(expr)'
print("=== Original ===")
print(sample)
print("\n=== Tokenized (Zero Regex) ===")
repaired = tokenize_repair(sample)
print(repaired)
