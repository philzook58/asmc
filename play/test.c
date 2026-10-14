int foo(int x, int y)
{
    return x + y;
}

int sum_array(int a[], int size)
{
    int acc = 0;
    for (int i = 0; i < size; i++)
    {
        acc += a[i];
    }
    return acc;
}
