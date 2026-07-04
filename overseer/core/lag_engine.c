#include <math.h>
#include <stddef.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

EXPORT int check_lag_arbitrage(double rithmic_price, double deriv_price, double threshold_pips)
{
    double delta = fabs(rithmic_price - deriv_price);
    return delta > threshold_pips ? 1 : 0;
}

EXPORT double calculate_cumulative_delta(double* bid_sizes, double* ask_sizes, int depth)
{
    if (bid_sizes == NULL || ask_sizes == NULL || depth <= 0)
        return 0.0;

    double total = 0.0;
    for (int i = 0; i < depth; i++)
        total += ask_sizes[i] - bid_sizes[i];

    return total;
}

EXPORT double atr_adaptive_threshold(double* atr_history, int length, double base_pips)
{
    if (atr_history == NULL || length <= 0 || base_pips <= 0.0)
        return base_pips;

    double sum = 0.0;
    for (int i = 0; i < length; i++)
        sum += atr_history[i];

    double mean = sum / (double)length;
    if (mean <= 0.0)
        return base_pips;

    double variance = 0.0;
    for (int i = 0; i < length; i++)
    {
        double diff = atr_history[i] - mean;
        variance += diff * diff;
    }

    double stdev = sqrt(variance / (double)length);
    double volatility_scale = 1.0 + (stdev / mean);
    return base_pips * volatility_scale;
}
