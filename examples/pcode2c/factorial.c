/* Adapted from pcode2c/examples/fact_iter/fact.c; see README.md. */
int fact(int x) {
  int result = 1;
loop_head:
  while (x != 0) {
loop_body:
    result = result * x;
    x = x - 1;
  }
loop_exit:
  return result;
}
