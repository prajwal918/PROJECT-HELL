encoded = 'z#o_kg"8!ij *$lmbbugmp"8!MPA?N"*!joqrcnadt#8Y}"l`nf 8$RL!-#gb$: 0ks6dlep4#- aqnlddugmps 9\\| r{pc!;#PGVHKHD`E?VEU@Z#* wscqobkc$: cft_`qt//7Afctoho/dmk$, obtquqrb!;#Lr-EJnovG2QGNQKjmEYtNv>> *$cmmofarkolSzqc <"LNO`?EI"*!tzqrgm 9#Sgrjmgb!Q_ngr Ssbbgpg +#mmactgno#8 Ehgbbhm ."qdswgags 9#CPMMEP{SF?JVIKD}IGQVOPHDBJ  ]{\\-#qcvtgmht 8}"khe#8 376/5:1363721;2691.!-#jccscDyqgpgs 9#1 *$tphbmCvripdt#8 3760624231448#* vrg`mFvnkrcc#; rtuc!~~'
target = "Rithmic Paper Trading"
source = "Sgrjmgb!Q_ngr Ssbbgpg"

# Find the shifts
shifts = [ord(t) - ord(s) for t, s in zip(target, source)]
print("Shifts (len={}): {}".format(len(shifts), shifts))

# Let's try to decrypt the whole string by repeating the shift pattern
decrypted = []
pattern_len = len(shifts)
for i, char in enumerate(encoded):
    shift = shifts[i % pattern_len]
    decrypted.append(chr(ord(char) + shift))
print("Decrypted:")
print("".join(decrypted))
