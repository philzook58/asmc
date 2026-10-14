set terminal svg size 1200,900 enhanced font 'sans,13'
set output 'scaling.svg'
set multiplot layout 2,2 title 'ASMC scaling: triangles mark timeouts; squares mark OOM RSS observations'
set grid
set key top left
set logscale x 2
set logscale y 10
set format y '%g'
set xlabel 'Buffer bytes'
set ylabel 'Wall seconds'
set title 'Symbolic 8-byte store: numeric RAM'
plot "memory-sat.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#1565c0" title "sat", "memory-sat.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#1565c0" notitle, "memory-sat.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#1565c0" notitle, "memory-z3.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#e65100" title "z3", "memory-z3.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#e65100" notitle, "memory-z3.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#e65100" notitle, "memory-cvc5.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#2e7d32" title "cvc5", "memory-cvc5.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#2e7d32" notitle, "memory-cvc5.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#2e7d32" notitle, "memory-bitwuzla.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#8e24aa" title "bitwuzla", "memory-bitwuzla.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#8e24aa" notitle, "memory-bitwuzla.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#8e24aa" notitle, "memory-kissat.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#795548" title "kissat", "memory-kissat.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#795548" notitle, "memory-kissat.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#795548" notitle
set xlabel 'Conditional branches'
set ylabel 'SSA steps'
set title 'Direct branches vs PC dispatch (same function)'
plot "branches-False.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#1565c0" title "direct", "branches-False.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#1565c0" notitle, "branches-False.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#1565c0" notitle, "branches-True.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#e65100" title "dispatch", "branches-True.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#e65100" notitle, "branches-True.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#e65100" notitle
set xlabel 'Dispatch unwind bound (two actual calls)'
set ylabel 'Peak reported RSS MiB'
set title 'Loose bounds and register-array scalarization'
plot "bounds-plain.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#1565c0" title "plain", "bounds-plain.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#1565c0" notitle, "bounds-plain.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#1565c0" notitle, "bounds-fields-768.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#e65100" title "fields-768", "bounds-fields-768.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#e65100" notitle, "bounds-fields-768.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#e65100" notitle, "bounds-fields-1024.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#2e7d32" title "fields-1024", "bounds-fields-1024.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#2e7d32" notitle, "bounds-fields-1024.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#2e7d32" notitle
set xlabel 'Admitted input/result bit width'
set ylabel 'Wall seconds'
set title 'Nonlinear modular arithmetic identity'
plot "multiply-sat.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#1565c0" title "sat", "multiply-sat.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#1565c0" notitle, "multiply-sat.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#1565c0" notitle, "multiply-z3.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#e65100" title "z3", "multiply-z3.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#e65100" notitle, "multiply-z3.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#e65100" notitle, "multiply-cvc5.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#2e7d32" title "cvc5", "multiply-cvc5.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#2e7d32" notitle, "multiply-cvc5.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#2e7d32" notitle, "multiply-bitwuzla.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#8e24aa" title "bitwuzla", "multiply-bitwuzla.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#8e24aa" notitle, "multiply-bitwuzla.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#8e24aa" notitle, "multiply-kissat.dat" using 1:2 with linespoints lw 2 pt 7 lc rgb "#795548" title "kissat", "multiply-kissat.dat" using 1:3 with points pt 9 ps 1.5 lc rgb "#795548" notitle, "multiply-kissat.dat" using 1:4 with points pt 4 ps 1.5 lc rgb "#795548" notitle
unset multiplot
