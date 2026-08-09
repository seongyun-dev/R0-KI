package com.oneloop.global.security;

import java.util.Collection;
import lombok.Getter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

@Getter
public class CustomUserDetails implements UserDetails {

    private final Long memberId;
    private final Long apartmentComplexId;
    private final Collection<? extends GrantedAuthority> authorities;

    public CustomUserDetails(
            Long memberId, Long apartmentComplexId, Collection<? extends GrantedAuthority> authorities) {
        this.memberId = memberId;
        this.apartmentComplexId = apartmentComplexId;
        this.authorities = authorities;
    }

    @Override
    public String getUsername() {
        return memberId.toString();
    }

    @Override
    public String getPassword() {
        return "";
    }
}
