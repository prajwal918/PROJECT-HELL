encoded = 'z#o_kg"8!ij *$lmbbugmp"8!MPA?N"*!joqrcnadt#8Y}"l`nf 8$RL!-#gb$: 0ks6dlep4#- aqnlddugmps 9\\| r{pc!;#PGVHKHD`E?VEU@Z#* wscqobkc$: cft_`qt//7Afctoho/dmk$, obtquqrb!;#Lr-EJnovG2QGNQKjmEYtNv>> *$cmmofarkolSzqc <"LNO`?EI"*!tzqrgm 9#Sgrjmgb!Q_ngr Ssbbgpg +#mmactgno#8 Ehgbbhm ."qdswgags 9#CPMMEP{SF?JVIKD}IGQVOPHDBJ  ]{\\-#qcvtgmht 8}"khe#8 376/5:1363721;2691.!-#jccscDyqgpgs 9#1 *$tphbmCvripdt#8 3760624231448#* vrg`mFvnkrcc#; rtuc!~~'

# We know some target substrings:
# "wscqobkc" -> "username"
# "obtquqrb" -> "password"
# "tzqrgm" -> "system"

# Let's find indices of these in the encoded string:
idx_user = encoded.find("wscqobkc")
idx_pass = encoded.find("obtquqrb")
idx_sys = encoded.find("tzqrgm")

print(f"Indices: user={idx_user}, pass={idx_pass}, sys={idx_sys}")

# Let's try different key lengths L
for L in range(1, 30):
    # If the key length is L, we want to find if there is a consistent key.
    # For each index i, key_index = i % L.
    # We can determine K[key_index] from the known mappings.
    K = {}
    consistent = True
    
    # Check "username" mapping
    for j, char in enumerate("wscqobkc"):
        idx = idx_user + j
        k_idx = idx % L
        diff = (ord(encoded[idx]) - ord("username"[j])) % 256
        if k_idx in K and K[k_idx] != diff:
            consistent = False
            break
        K[k_idx] = diff
        
    if not consistent:
        continue
        
    # Check "password" mapping
    for j, char in enumerate("obtquqrb"):
        idx = idx_pass + j
        k_idx = idx % L
        diff = (ord(encoded[idx]) - ord("password"[j])) % 256
        if k_idx in K and K[k_idx] != diff:
            consistent = False
            break
        K[k_idx] = diff
        
    if not consistent:
        continue

    # Check "system" mapping
    for j, char in enumerate("tzqrgm"):
        idx = idx_sys + j
        k_idx = idx % L
        diff = (ord(encoded[idx]) - ord("system"[j])) % 256
        if k_idx in K and K[k_idx] != diff:
            consistent = False
            break
        K[k_idx] = diff
        
    if not consistent:
        continue

    # If we get here, we found a consistent key length L!
    print(f"\nFOUND consistent key length L={L}")
    # Fill in any missing key elements
    key_list = [K.get(i, None) for i in range(L)]
    print(f"Partial Key: {key_list}")
    
    # Let's try to decrypt the whole string using this key
    dec = []
    for i, char in enumerate(encoded):
        k_idx = i % L
        if k_idx in K:
            dec.append(chr((ord(char) - K[k_idx]) % 256))
        else:
            dec.append("?")
    print("Decrypted:")
    print("".join(dec))
