package com.oneloop.global.security;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.oneloop.map.service.NavigationWaypointService;
import com.oneloop.map.service.RobotNavigationConfigService;
import com.oneloop.map.service.ZoneService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@ActiveProfiles("test")
@SpringBootTest
@AutoConfigureMockMvc
class NavigationSecurityIntegrationTest {

    @Autowired private MockMvc mockMvc;

    @MockitoBean private RobotNavigationConfigService robotNavigationConfigService;
    @MockitoBean private NavigationWaypointService navigationWaypointService;
    @MockitoBean private ZoneService zoneService;

    @Test
    void robotRoleCanReadRobotNavigationConfig() throws Exception {
        mockMvc.perform(
                        get("/api/robot/navigation-config")
                                .with(authentication(robotAuthentication())))
                .andExpect(status().isOk());
    }

    @Test
    void administratorCannotReadRobotNavigationConfig() throws Exception {
        mockMvc.perform(
                        get("/api/robot/navigation-config")
                                .with(authentication(adminAuthentication())))
                .andExpect(status().isForbidden());
    }

    @Test
    void robotCannotReadAdministratorWaypointOrZoneApi() throws Exception {
        mockMvc.perform(get("/api/map/31/waypoints").with(authentication(robotAuthentication())))
                .andExpect(status().isForbidden());
        mockMvc.perform(get("/api/map/31/zones").with(authentication(robotAuthentication())))
                .andExpect(status().isForbidden());
    }

    @Test
    void administratorCanReadAdministratorWaypointAndZoneApi() throws Exception {
        mockMvc.perform(get("/api/map/31/waypoints").with(authentication(adminAuthentication())))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/map/31/zones").with(authentication(adminAuthentication())))
                .andExpect(status().isOk());
    }

    @Test
    void unauthenticatedRobotNavigationRequestIsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/robot/navigation-config")).andExpect(status().isUnauthorized());
    }

    private Authentication robotAuthentication() {
        return new UsernamePasswordAuthenticationToken(
                17L, null, List.of(new SimpleGrantedAuthority("ROLE_ROBOT")));
    }

    private Authentication adminAuthentication() {
        CustomUserDetails principal = new CustomUserDetails(1L, 2L, List.of());
        return new UsernamePasswordAuthenticationToken(principal, null, principal.getAuthorities());
    }
}
