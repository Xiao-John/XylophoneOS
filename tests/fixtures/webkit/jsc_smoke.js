// SPDX-License-Identifier: Apache-2.0

function triangular(limit) {
    let sum = 0;
    for (let item = 1; item <= limit; ++item)
        sum += item;
    return sum;
}

const totals = [3, 5, 8].map(triangular);
if (totals.join(",") !== "6,15,36")
    throw new Error("unexpected interpreter result: " + totals.join(","));
print("CLARKE_JSC_LLINT_PASS " + totals.join(","));
