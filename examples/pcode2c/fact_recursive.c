/* Core of pcode2c/examples/fact_rec; bounded against iterative factorial. */
int fact_recursive(int n) {
  return n == 0 ? 1 : n * fact_recursive(n - 1);
}
