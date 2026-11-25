package main

import "testing"

func TestPromotionRotationWithIncompleteDates(t *testing.T) {
	candidates := []string{"jenkinsci", "r_new", "r_funny", "r_old"}
	dates := D{"r_funny": date(20), "r_old": date(10), "inactive": date(30)}
	// The older worker recorded Jenkins repeatedly despite its missing date.
	promoted := A{"jenkinsci", "jenkinsci"}
	for _, want := range []string{"r_funny", "r_old", "r_new"} {
		got, reset := nextPromotion(candidates, dates, promoted)
		if got != want || reset {
			t.Fatalf("rotation after %v chose %q (reset %v), want %q", promoted, got, reset, want)
		}
		promoted = append(promoted, got)
	}
	if got, reset := nextPromotion(candidates, dates, promoted); got != "r_funny" || !reset {
		t.Fatalf("exhausted rotation chose %q (reset %v), want first channel and reset", got, reset)
	}
}

func TestPromotionRotationWithoutDateView(t *testing.T) {
	candidates := []string{"r_funny", "jenkinsci"}
	if got, reset := nextPromotion(candidates, nil, A{"jenkinsci"}); got != "r_funny" || reset {
		t.Fatalf("rotation without dates chose %q (reset %v), want unpromoted channel", got, reset)
	}
}
