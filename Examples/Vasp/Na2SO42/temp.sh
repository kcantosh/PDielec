pdielec -matrix ptfe -sigma 5 \
                         -needle 0 0 1 -ellipsoid 0 0 1 0.5 -plate 1 0 0 \
                         -LO 1 1 1 \
                         -csv command.csv \
                         -eckart -program vasp OUTCAR
