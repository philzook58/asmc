#![cfg_attr(not(kani), no_std)]

// The native compiler and Kani consume this same Rust source.
#[no_mangle]
pub extern "C" fn add_one(x: u64) -> u64 {
    x.wrapping_add(1)
}

// Deliberately wrong machine implementation for the scalar negative control.
#[no_mangle]
pub extern "C" fn add_two(x: u64) -> u64 {
    x.wrapping_add(2)
}

#[no_mangle]
pub unsafe extern "C" fn swap_words(a: *mut u32, b: *mut u32) {
    let tmp = *a;
    *a = *b;
    *b = tmp;
}

// This mutant works for distinct objects, but fails when both pointers alias.
#[no_mangle]
pub unsafe extern "C" fn swap_xor(a: *mut u32, b: *mut u32) {
    *a ^= *b;
    *b ^= *a;
    *a ^= *b;
}

#[cfg(kani)]
mod proofs {
    extern "C" {
        fn machine_add_one(x: u64) -> u64;
        fn machine_swap(a: *mut u32, b: *mut u32) -> u32;
    }

    #[kani::proof]
    fn scalar_equivalence() {
        let x: u64 = kani::any();
        let actual = unsafe { machine_add_one(x) };
        assert_eq!(actual, super::add_one(x));
    }

    #[kani::proof]
    fn swap_equivalence() {
        let mut a: u32 = kani::any();
        let mut b: u32 = kani::any();
        let (mut ref_a, mut ref_b) = (a, b);
        let same_object: bool = kani::any();
        // Raw pointers deliberately admit aliasing without creating two
        // simultaneous &mut references to the same Rust object.
        let p = core::ptr::addr_of_mut!(a);
        let q = if same_object { p } else { core::ptr::addr_of_mut!(b) };
        let ref_p = core::ptr::addr_of_mut!(ref_a);
        let ref_q = if same_object { ref_p } else { core::ptr::addr_of_mut!(ref_b) };
        unsafe {
            super::swap_words(ref_p, ref_q);
            assert_eq!(machine_swap(p, q), 0);
        }
        assert_eq!(a, ref_a);
        assert_eq!(b, ref_b);
    }
}
